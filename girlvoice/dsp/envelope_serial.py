#!/usr/bin/env python3
import os
import math
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream
from amaranth.lib import memory

from amaranth.sim import Simulator
from girlvoice.dsp.tdm_slice import TDMMultiply
from girlvoice.stream import stream_get, stream_put
from girlvoice.dsp.utils import generate_chirp, generate_impulse


"""
An Envelope follower is essentially a special kind of low-pass filter
Its purpose is to trace the "envelope" of a signal. In a channel vocoder, this "envelope"
can be used to vary the amplification of one of the carrier signals.

This filter is implemented as an IIR low-pass filter with parameterized options for attack and decay
Largely inspired by the implementation described here:
https://kferg.dev/posts/2020/audio-reactive-programming-envelope-followers

Attack and decay input parameters represent the time to decay halfway (halflife) in milliseconds

"""


class SerialEnvelopeFollower(wiring.Component):
    def __init__(
        self,
        sample_width=24,
        fs=48000,
        attack_halflife=10,
        decay_halflife=20,
        instances = 10,
        mult_slice: TDMMultiply = None,
        formal=False,
    ):
        self.formal = formal
        self.sample_width = sample_width
        self.fraction_width = sample_width - 1
        self.gate = 100

        self.instances = instances

        attack_hl_samples = fs * attack_halflife / 1000.0
        attack = math.exp(-1 / attack_hl_samples)
        attack_comp = 1 - attack

        decay_hl_samples = fs * decay_halflife / 1000.0
        decay = math.exp(-1 / decay_hl_samples)
        decay_comp = 1 - decay
        print(f"Envelope Decay parameter: {decay}")
        print(f"Envelope Attack parameter: {attack}")

        self.attack_fp = C(
            int(attack * (2 ** (self.fraction_width))), signed(sample_width)
        )
        self.attack_comp = C(
            int(attack_comp * (2 ** (self.fraction_width))), signed(sample_width)
        )

        self.decay_fp = C(
            int(decay * (2 ** (self.fraction_width))), signed(sample_width)
        )
        self.decay_comp = C(
            int(decay_comp * (2 ** (self.fraction_width))), signed(sample_width)
        )

        attack_quant = self.attack_fp.value / 2**self.fraction_width
        decay_quant = self.decay_fp.value / 2**self.fraction_width
        print(f"Envelope Decay parameter quantized: {decay_quant}")
        print(f"Envelope Attack parameter quantized: {attack_quant}")

        if mult_slice is not None:
            assert mult_slice.sample_width >= self.sample_width
            self.mult = mult_slice
        else:
            self.mult = None

        signature = {}
        for i in range(self.instances):
            signature[f"sink_{i}"] = In(stream.Signature(signed(sample_width)))
            signature[f"source_{i}"] = Out(stream.Signature(signed(sample_width)))

        super().__init__(signature)

    def source(self, i):
        return self.__dict__[f"source_{i}"]

    def sink(self, i):
        return self.__dict__[f"sink_{i}"]

    def sources(self):
        return [self.__dict__[f"source_{i}"] for i in range(self.instances)]

    def sinks(self):
        return [self.__dict__[f"sink_{i}"] for i in range(self.instances)]

    def elaborate(self, platform):
        m = Module()

        # ---------- Core DSP registers and parameter control logic ---------
        mac_width = self.sample_width * 2
        acc = Signal(signed(mac_width))
        acc_quant = Signal(signed(self.sample_width))
        x = Signal(signed(self.sample_width))
        y = Signal(signed(self.sample_width))
        output_sample = Signal(signed(self.sample_width))

        param = Signal(signed(self.sample_width))
        param_comp = Signal(signed(self.sample_width))
        m.d.comb += param.eq(Mux(abs(x) > y, self.attack_fp, self.decay_fp))
        m.d.comb += param_comp.eq(Mux(abs(x) > y, self.attack_comp, self.decay_comp))

        # ----------- Feedback term memory ---------------

        # Index of current filter instance being handled
        cur_inst = Signal(range(self.instances))
        # Feedback sample memory for each channel
        m.submodules.mem = mem = memory.Memory(
            shape=signed(self.sample_width),
            depth=self.instances,
            init = [0] * self.instances
        )

        rd_port: memory.ReadPort = mem.read_port()
        wr_port: memory.WritePort = mem.write_port()
        m.d.comb += [
            rd_port.en.eq(1),
            rd_port.addr.eq(cur_inst),

            wr_port.data.eq(y),
            wr_port.addr.eq(cur_inst)
        ]


        # ------- Souce Muxing control signals --------
        # The global ouput valid signal, all individual output valids are masked by this
        output_sample_valid = Signal()
        # current output sample ready signal
        cur_source_ready = Signal()

        # Shift register that selects the individual output valid signal to control.
        output_valid_mask = Signal(self.instances, init=1)

        ready_vec = Signal(self.instances)
        for i in range(self.instances):
            out = self.source(i)
            m.d.comb += out.payload.eq(output_sample)
            m.d.comb += out.valid.eq(output_valid_mask[i] & output_sample_valid)
            m.d.comb += ready_vec.bit_select(i, 1).eq(out.ready)
        m.d.comb += cur_source_ready.eq((ready_vec & output_valid_mask).any())


        # -------- Sink Muxing control signals ---------

        ## Payload muxing
        # Concatenate all the incoming samples into a giant bit vector
        sink_vector = Signal(self.instances * self.sample_width)
        for i in range(self.instances):
            start_idx = i * self.sample_width
            end_idx = (i + 1) * self.sample_width
            m.d.comb += sink_vector[start_idx:end_idx].eq(self.sink(i).payload)

        # Now we can mux out of our giant bit vector based on the current channel we are handling
        m.d.comb += x.eq(sink_vector.word_select(cur_inst, self.sample_width))

        ## Ready muxing

        # Global input ready signal
        input_sample_ready = Signal()

        # Shift register that selects the individual input ready signal to control.
        input_ready_mask = Signal(self.instances, init=1)

        # Bit vector containing all input valid signals concatenated together
        input_valid_vec = Signal(self.instances)
        for i in range(self.instances):
            input_i = self.sink(i)
            m.d.comb += [
                input_i.ready.eq(input_sample_ready & input_ready_mask[i]),
                input_valid_vec[i].eq(input_i.valid),
            ]

        # Valid signal for the currently selected sink stream
        cur_sink_valid = Signal()
        # The current sink is valid if its respective bit in the vector of all ready bits is high
        m.d.comb += cur_sink_valid.eq((input_valid_vec & input_ready_mask).any())

        if self.mult is None:
            mac_out = Signal(signed(mac_width))
            mac_in_1 = Signal(signed(self.sample_width))
            mac_in_2 = Signal(signed(self.sample_width))
            m.d.comb += mac_out.eq(acc + (mac_in_1 * mac_in_2))
            # m.d.sync += Assert(acc >= 0, "Envelope accumulator overflow")

            # Quantized accumulator output
            m.d.comb += acc_quant.eq((mac_out) >> (self.fraction_width))
            m.d.comb += output_sample.eq(acc_quant)

            # # Saturated sample output:
            # with m.If(acc_quant >= 0):
            #     m.d.comb += output_sample.eq(acc_quant)
            # with m.Else():
            #     m.d.comb += output_sample.eq(
            #         2 ** (self.sample_width - 1) - 1
            #     )


            with m.FSM():
                with m.State("LOAD"):
                    m.d.comb += output_sample_valid.eq(0)
                    m.d.comb += input_sample_ready.eq(1)
                    with m.If(cur_sink_valid):
                        m.d.sync += acc.eq(0)
                        m.d.sync += mac_in_1.eq(param_comp)
                        m.d.sync += mac_in_2.eq(abs(x))
                        # m.d.sync += mac_in_2.eq(x)
                        # m.d.sync += y.eq(rd_port.data)
                        m.d.sync += input_ready_mask.eq(input_ready_mask.rotate_left(1))
                        m.next = "MULT_Y"
                with m.State("MULT_Y"):
                    m.d.comb += y.eq(rd_port.data)
                    m.d.sync += acc.eq(mac_out)
                    m.d.sync += mac_in_1.eq(param)
                    m.d.sync += mac_in_2.eq(y)
                    m.d.sync += wr_port.en.eq(1)
                    m.next = "READY"
                with m.State("READY"):
                    m.d.sync += wr_port.en.eq(0)
                    m.d.comb += output_sample_valid.eq(1)
                    m.d.comb += y.eq(output_sample)
                    # Saturation logic:
                    with m.If(cur_source_ready):
                        m.d.sync += output_valid_mask.eq(output_valid_mask.rotate_left(1))
                        with m.If(cur_inst != (self.instances - 1)):
                            m.d.sync += cur_inst.eq(cur_inst + 1)
                        with m.Else():
                            m.d.sync += cur_inst.eq(0)
                        # m.d.sync += Assert(self.source.payload >= 0, "Envelope follower gave negative output")
                        m.next = "LOAD"

        else:
            mac_out = self.mult.source
            mac_in_1, mac_in_2, mult_valid = self.mult.get_next_thread_ports()

            m.d.comb += acc_quant.eq(acc >> self.fraction_width)

            m.d.comb += self.source.payload.eq(Mux(acc_quant > self.gate, acc_quant, 0))
            with m.If(self.sink.valid & self.sink.ready):
                m.d.sync += mac_in_1.eq(param_comp)
                m.d.sync += mac_in_2.eq(abs(x))
            with m.If(self.source.valid & self.source.ready):
                m.d.sync += self.source.valid.eq(0)
                m.d.sync += y.eq(self.source.payload)
                if self.formal:
                    m.d.sync += Assert(self.source.payload >= 0)

            with m.FSM():
                with m.State("LOAD"):
                    m.d.comb += self.sink.ready.eq(~self.source.valid & mult_valid)

                    with m.If(self.sink.valid & self.sink.ready):
                        m.d.sync += acc.eq(0)
                        m.next = "MULT_Y"

                with m.State("MULT_Y"):
                    with m.If(mult_valid):
                        m.d.sync += acc.eq(mac_out)
                        m.d.sync += mac_in_1.eq(param)
                        m.d.sync += mac_in_2.eq(y)
                        m.next = "WAIT"

                with m.State("WAIT"):
                    with m.If(mult_valid):
                        m.d.sync += acc.eq(mac_out + acc)
                        m.d.sync += self.source.valid.eq(1)
                        m.next = "LOAD"

        return m


# Testbench ----------------------------------------


def generate_ramp(freq, duration, fs, sample_width):
    num_samples = int(duration * fs)
    t = np.linspace(0, duration, num_samples)
    input_samples = signal.sawtooth(2 * np.pi * freq * t) * t
    input_samples *= 2 ** (sample_width - 1)
    input_samples = np.flip(input_samples)
    input_samples[0 : int(0.1 * num_samples)] = 0
    return (t, input_samples)


def run_sim():
    clk_freq = 60e6
    bit_width = 16
    fs = 48000

    m = Module()
    # m.submodules.mult = mult = TDMMultiply(bit_width, num_threads=2)
    num_inst = 4
    m.submodules.dut = env = SerialEnvelopeFollower(
        sample_width=bit_width, fs=fs, mult_slice=None, attack_halflife=0.75, decay_halflife=2.5, instances=num_inst,
    )

    # m.d.comb += [source.ready.eq(1) for source in env.sources()]

    duration = 0.1

    test_sig_freq = 500
    # (t, input_samples) = generate_ramp(test_sig_freq, duration, fs, bit_width)
    # start_freq = 10
    # end_freq = 10000
    # (t, input_samples) = generate_chirp(duration, fs, start_freq, end_freq, bit_width)
    # t, input_samples = generate_impulse(duration, fs, bit_width)

    input_samples = []
    for i in range(num_inst):
        t, impulse = generate_impulse(duration, fs, bit_width, start_time=(i * (duration / num_inst)))
        input_samples.append(impulse)

    output_samples = [[] for _ in range(num_inst) ]
    async def tb(ctx):
        samples_processed = 0

        for sample_idx in range(len(t)):
            for i in range(num_inst):
                sink = env.sink(i)
                source = env.source(i)
                await stream_put(ctx, sink, int(input_samples[i][sample_idx]))
                output_samples[i].append(await stream_get(ctx, source))


            await ctx.tick()
            samples_processed += 1
            if samples_processed % 1000 == 0:
                print(f"{samples_processed}/{len(t)} Samples processed")

    sim = Simulator(m)
    sim.add_clock(1 / clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(env).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        # bode_plot(fs, duration, end_freq, input_samples, output_samples)
        ax2 = plt.subplot(111)
        for i in range(num_inst):
            ax2.plot(t, input_samples[i], alpha=0.5, label=f"Input_{i}")
            ax2.plot(t, output_samples[i], alpha=0.5, label=f"Output_{i}")
        ax2.set_xlabel("time (s)")
        plt.title("Envelope Follower")
        plt.grid(True)
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", borderaxespad=0.0)
        plt.legend()
        # plt.savefig(f"{type(dut).__name__}.png")
        plt.show()


if __name__ == "__main__":
    run_sim()
