#!/usr/bin/env python
from math import ceil, log2
import os
import numpy as np
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream, memory
import amaranth_soc.wishbone.bus as wishbone
from amaranth_soc.wishbone.sram import WishboneSRAM
from amaranth_soc.memory import MemoryMap
from amaranth.sim import Simulator

from girlvoice.stream import stream_get


class StaticSineSynth(wiring.Component):
    def __init__(self, target_frequency, fs, sample_width):
        assert target_frequency <= fs / 2

        super().__init__(
            {
                "en": In(1),
                "source": Out(
                    stream.Signature(signed(sample_width), always_valid=True)
                ),
            }
        )

        self.sample_width = sample_width
        self.frequency = target_frequency
        self.fs = fs

        phase_bit_width = 8
        t = np.linspace(0, 2 * np.pi, 2**phase_bit_width)
        y = np.sin(t)
        self.lut = Array(
            C(int(y_i * (2 ** (sample_width - 1))), signed(sample_width)) for y_i in y
        )

        self.oversampling = 8
        self.N = N = phase_bit_width + self.oversampling
        self.delta_f = int((2**N * target_frequency) / fs)

        actual_freq = self.delta_f * fs / 2**N
        print(
            f"target synth freq: {self.frequency} hz, achieved {actual_freq} hz, phase resulution {n} bits, increment: {self.delta_f}"
        )

    def elaborate(self, platform):
        m = Module()

        N = self.N
        idx = Signal(N, reset=1)
        m.d.comb += self.source.payload.eq(self.lut[idx >> self.oversampling])

        with m.If(self.en):
            with m.If(self.source.ready & self.source.valid):
                m.d.sync += idx.eq(idx + self.delta_f)

        return m


class ParallelSineSynth(wiring.Component):
    def __init__(self, target_frequencies, fs, sample_width, phase_bits=8):
        self.num_outputs = len(target_frequencies)
        self.sample_width = sample_width
        self.fs = fs

        self.phase_bit_width = phase_bit_width = phase_bits

        # Generate Sine LUT, use symmetry of sine function to reduce LUT size
        t = np.linspace(0, np.pi, 2 ** (phase_bit_width - 1))
        y = np.sin(t)

        self.lut = [
            C(int(y_i * (2 ** (sample_width - 1))), signed(sample_width)) for y_i in y
        ]

        self.oversampling = 8

        # N = Total number of bits for phase accumulator
        self.N = N = phase_bit_width + self.oversampling

        self.del_f = [int((2**N * f) / fs) for f in target_frequencies]

        signature = {}
        for i in range(self.num_outputs):
            del_f = self.del_f[i]
            target_freq = target_frequencies[i]
            actual_freq = del_f * (fs / 2**N)

            print(
                f"target synth freq: {target_freq} hz, achieved {actual_freq} hz, increment: {del_f}"
            )

            signature[f"source_{i}"] = Out(stream.Signature(signed(sample_width)))

        # If I actually use 18 bit samples at some point this will fuck me
        granularity = 8
        self.wavetable_ram = WishboneSRAM(
            data_width=32,
            granularity=granularity,
            size=len(self.lut) * 32 // 8,
            init=self.lut
        )

        signature["wb_bus"] = In(self.wavetable_ram.wb_bus.signature)
        super().__init__(signature=signature)

        self.wb_bus.memory_map = self.wavetable_ram.wb_bus.memory_map

    def source(self, i):
        return self.__dict__[f"source_{i}"]

    def elaborate(self, platform):
        m = Module()

        # m.submodules.rom = wavetable_rom = memory.Memory(
        #     shape=signed(self.sample_width), depth=len(self.lut), init=self.lut
        # )
        m.submodules.ram = self.wavetable_ram
        rd_port_wavetable: memory.ReadPort = self.wavetable_ram._mem.read_port()
        m.d.comb += rd_port_wavetable.en.eq(1)

        N = self.N
        idx = Signal(len(self.del_f), reset=0)

        phase_delta = Array([C(df, N) for df in self.del_f])
        m.submodules.phase_delta_rom = delta_rom = memory.Memory(
            shape=N, depth=len(self.del_f), init=self.del_f
        )
        delta_rd_port: memory.ReadPort = delta_rom.read_port()
        delta_i = Signal(N)
        m.d.comb += delta_rd_port.en.eq(1)
        m.d.comb += delta_rd_port.addr.eq(idx)
        m.d.comb += delta_i.eq(delta_rd_port.data)

        m.submodules.phase_offset_mem = phase_mem = memory.Memory(
            shape=N, depth=self.num_outputs, init=[0] * self.num_outputs
        )
        rd_port_phase: memory.ReadPort = phase_mem.read_port()
        cur_phase = Signal(N)
        m.d.comb += rd_port_phase.en.eq(1)
        m.d.comb += rd_port_phase.addr.eq(idx)
        m.d.comb += cur_phase.eq(rd_port_phase.data)

        wr_port_phase: memory.WritePort = phase_mem.write_port()
        next_phase = Signal(N)
        m.d.comb += wr_port_phase.data.eq(next_phase)
        m.d.comb += wr_port_phase.addr.eq(idx)
        prev_phase = Signal(N)
        m.d.comb += next_phase.eq(prev_phase + delta_i)

        phase_i = Signal(self.phase_bit_width)
        wav_sample = Signal(self.sample_width)
        m.d.comb += rd_port_wavetable.addr.eq(phase_i[:-1])
        m.d.comb += wav_sample.eq(
            Mux(phase_i[-1], rd_port_wavetable.data, -rd_port_wavetable.data)
        )

        # The global valid signal, all individual output valids are masked by this
        samp_valid = Signal()

        cur_ready = Signal()

        # Barrel shifter for individual output valids.
        # valid_regs = [Signal() if i != 0 else Signal(init=1) for i in range(self.num_outputs)]
        valid_regs = Signal(self.num_outputs, init=1)

        ready_vec = Signal(self.num_outputs)
        for i in range(self.num_outputs):
            out = self.source(i)
            m.d.comb += out.payload.eq(wav_sample)
            m.d.comb += out.valid.eq(valid_regs[i] & samp_valid)
            m.d.comb += ready_vec.bit_select(i, 1).eq(out.ready)
        m.d.comb += cur_ready.eq((ready_vec & valid_regs).any())

        with m.If(cur_ready & samp_valid):
            m.d.sync += samp_valid.eq(0)
            m.d.comb += wr_port_phase.en.eq(1)
            with m.If(idx == len(self.del_f) - 1):
                m.d.sync += idx.eq(0)
            with m.Else():
                m.d.sync += idx.eq(idx + 1)

            with m.If(valid_regs[-1] == 1):
                m.d.sync += valid_regs.eq(1)
            with m.Else():
                m.d.sync += valid_regs.eq(valid_regs << 1)

        with m.FSM():
            with m.State("LOAD_PHASE"):
                m.d.sync += phase_i.eq(cur_phase >> self.oversampling)
                m.d.sync += prev_phase.eq(cur_phase)
                m.next = "READ_AMP"
            with m.State("READ_AMP"):
                m.d.sync += samp_valid.eq(1)
                m.next = "READY"
            with m.State("READY"):
                with m.If(cur_ready):
                    m.next = "WAIT"
            with m.State("WAIT"):
                m.next = "LOAD_PHASE"

        return m


def run_parallel_sim():
    from scipy.io import wavfile
    import matplotlib.pyplot as plt
    from girlvoice.stream import stream_get

    clk_freq = 1e6
    bit_width = 16
    target_freqs = [100, 200, 300, 400]
    fs = 48000
    duration = 0.1

    dut = ParallelSineSynth(
        target_frequencies=target_freqs,
        fs=fs,
        sample_width=bit_width,
        phase_bits=8,
    )

    num_samples = int(fs * duration)

    sim_steps = int(duration * clk_freq)
    t = np.linspace(0, 1, num_samples)
    t = t * duration
    output_samples = [[] for _ in range(len(target_freqs))]

    async def tb(ctx):
        print(f"beginning sim, samples: {num_samples}")
        samples_processed = 0
        for i in range(num_samples * len(target_freqs)):
            output_idx = i % len(target_freqs)
            output_samples[output_idx].append(
                await stream_get(ctx, dut.source(output_idx))
            )
            samples_processed += 1
            if samples_processed % 1000 == 0:
                print(f"{samples_processed}/{len(t)} Samples processed")

    sim = Simulator(dut)
    sim.add_clock(1 / clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()

    ax1 = plt.subplot(122)
    ax2 = plt.subplot(121)
    fft_freqs = np.fft.fftfreq(len(output_samples[0]), 1 / fs)
    for i in range(len(target_freqs)):
        wavfile.write(
            f"sine_synth_test_{target_freqs[i]}hz.wav",
            rate=fs,
            data=np.array(output_samples[i], dtype=np.int16),
        )
        fft = np.fft.fft(output_samples[i])
        ax1.plot(
            fft_freqs[: len(fft) // 2],
            fft[: len(fft) // 2],
            label=f"FFT of Output @ {target_freqs[i]}",
        )
        ax2.plot(t, output_samples[i], alpha=0.5, label=f"Output @ {target_freqs[i]}")
    ax1.legend()

    ax2.set_xlabel("time (s)")
    plt.title("Sine Synth")
    plt.grid(True)
    plt.legend()
    # plt.savefig(f"{type(dut).__name__}.png")
    plt.show()


def run_static_sim():
    from scipy.io import wavfile
    import matplotlib.pyplot as plt

    clk_freq = 1e6
    bit_width = 16
    target_freq = 1000
    fs = 48000
    duration = 0.1

    phase_bit_width = 16
    t = np.linspace(0, 2 * np.pi, 2**phase_bit_width)
    y = np.sin(t)
    lut = Array(C(int(y_i * (2 ** (bit_width - 1))), signed(bit_width)) for y_i in y)
    dut = StaticSineSynth(
        target_frequency=target_freq,
        fs=fs,
        sample_width=bit_width,
        sine_lut=lut,
        clk_sync_freq=clk_freq,
    )

    num_samples = int(fs * duration)

    sim_steps = int(duration * clk_freq)
    t = np.linspace(0, 1, num_samples)
    t = t * duration
    output_samples = []

    async def tb(ctx):
        print(
            f"beginning sim, wait cycles: {int(clk_freq / fs)}, samples: {num_samples}"
        )
        samples_processed = 0
        steps = 0
        ctx.set(dut.en, 1)
        for _ in range(num_samples):
            output_samples.append(ctx.get(dut.source.payload))
            samples_processed += 1
            if samples_processed % 1000 == 0:
                print(f"{samples_processed}/{len(t)} Samples processed")
            for i in range(int(clk_freq / fs)):
                await ctx.tick()
            steps += 1
        print(samples_processed)

    sim = Simulator(dut)
    sim.add_clock(1 / clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()

    wavfile.write(
        "sine_synth_test.wav", rate=fs, data=np.array(output_samples, dtype=np.int16)
    )
    ax2 = plt.subplot(111)
    ax2.plot(t, output_samples, alpha=0.5, label="Output")
    ax2.set_xlabel("time (s)")
    plt.title("Sine Synth")
    plt.grid(True)
    plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", borderaxespad=0.0)
    plt.legend()
    # plt.savefig(f"{type(dut).__name__}.png")
    plt.show()


if __name__ == "__main__":
    run_parallel_sim()
