#!/usr/bin/env python
from math import ceil, log2
import os
import numpy as np
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream, memory
from amaranth.sim import Simulator

from girlvoice.stream import stream_get

class StaticSineSynth(wiring.Component):

    def __init__(self, target_frequency, fs, clk_sync_freq, sample_width):

        assert target_frequency <= fs/2

        super().__init__({
            "en": In(1),
            "source": Out(stream.Signature(signed(sample_width), always_valid=True))
        })

        self.sample_width = sample_width
        self.frequency = target_frequency
        self.fs = fs

        phase_bit_width = 8
        t = np.linspace(0, 2*np.pi, 2**phase_bit_width)
        y = np.sin(t)
        self.lut = Array(C(int(y_i*(2**(sample_width-1))), signed(sample_width)) for y_i in y)

        self.oversampling = 8
        self.N = N = phase_bit_width + self.oversampling
        self.delta_f = int((2**N * target_frequency) / fs)

        actual_freq = self.delta_f * fs / 2**N
        print(f"Target synth freq: {self.frequency} Hz, achieved {actual_freq} Hz, phase resulution {N} bits, increment: {self.delta_f}")

    def elaborate(self, platform):
        m = Module()

        N = self.N
        sign = Signal()
        idx = Signal(N, reset=0)

        m.d.comb += self.source.payload.eq(self.lut[idx >> self.oversampling])


        with m.If(self.en):
            with m.If(self.source.ready & self.source.valid):
                m.d.sync += idx.eq(idx + self.delta_f)


        return m

class ParallelSineSynth(wiring.Component):
    def __init__(self, target_frequencies, fs, sample_width, phase_bits=8):
        super().__init__({
            "en": In(1),
            "source": Out(stream.Signature(signed(sample_width)))
        })

        self.sample_width = sample_width
        self.fs = fs

        phase_bit_width = phase_bits

        # Generate Sine LUT, use symmetry of sine function to reduce LUT size
        t = np.linspace(0, np.pi, 2**(phase_bit_width-1))
        y = np.sin(t)


        self.lut = [C(int(y_i*(2**(sample_width-1))), signed(sample_width)) for y_i in y]

        self.oversampling = 8

        # N = Total number of bits for phase accumulator
        self.N = N = phase_bit_width + self.oversampling

        self.del_f = [int((2**N * f) / fs) for f in target_frequencies]


    def elaborate(self, platform):
        m = Module()

        m.submodules.rom = rom = memory.Memory(shape=signed(self.sample_width), depth=len(self.lut), init=self.lut)
        r_port: memory.ReadPort = rom.read_port()
        m.d.comb += r_port.en.eq(1)

        N = self.N
        idx = Signal(len(self.del_f), reset=0)

        phase_delta = Array([C(df, N) for df in self.del_f])
        phase_array = Array([Signal(N, reset=0) for _ in range(len(self.del_f))])
        phase_i = Signal(N)

        with m.If(self.source.ready & self.source.valid):
            with m.If(idx == len(self.del_f) - 1):
                m.d.sync += idx.eq(0)
            with m.Else():
                m.d.sync += idx.eq(idx + 1)

        m.d.comb += r_port.addr.eq(phase_i[:-1])
        with m.FSM():
            with m.State("LOAD_PHASE"):
                # with m.If(self.source.ready):
                m.d.sync += phase_i.eq(phase_array[idx] >> self.oversampling)
                m.next = "READ_AMP"
            with m.State("READ_AMP"):
                m.d.sync += self.source.valid.eq(1)
                m.next = "READY"
            with m.State("READY"):
                m.d.sync += self.source.payload.eq(Mux(phase_i.bit_select(N-1, 1), r_port.data, -r_port.data))
                with m.If(self.source.ready & self.source.valid):
                    m.d.sync += self.source.valid.eq(0)
                    m.d.sync += phase_array[idx].eq(phase_array[idx] + phase_delta[idx])
                    m.next = "LOAD_PHASE"


        return m

def run_sim():
    from scipy.io import wavfile
    import matplotlib.pyplot as plt
    clk_freq = 1e6
    bit_width = 16
    target_freq = 1000
    fs = 48000
    duration = 0.1

    phase_bit_width = 16
    t = np.linspace(0, 2*np.pi, 2**phase_bit_width)
    y = np.sin(t)
    lut = Array(C(int(y_i*(2**(bit_width-1))), signed(bit_width)) for y_i in y)
    dut = StaticSineSynth(target_frequency=target_freq, fs=fs, sample_width=bit_width, sine_lut=lut, clk_sync_freq=clk_freq)

    num_samples = int(fs * duration)

    sim_steps = int(duration * clk_freq)
    t = np.linspace(0, 1, num_samples)
    t = t * duration
    output_samples = []
    async def tb(ctx):
        print(f"beginning sim, wait cycles: {int(clk_freq/fs)}, samples: {num_samples}")
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
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()

    wavfile.write("sine_synth_test.wav", rate=fs, data=np.array(output_samples, dtype=np.int16))
    ax2 = plt.subplot(111)
    ax2.plot(t, output_samples, alpha=0.5, label="Output")
    ax2.set_xlabel('time (s)')
    plt.title('Sine Synth')
    plt.grid(True)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
    plt.legend()
    # plt.savefig(f"{type(dut).__name__}.png")
    plt.show()

if __name__ == "__main__":
    run_sim()

