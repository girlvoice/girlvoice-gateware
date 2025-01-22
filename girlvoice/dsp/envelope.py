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

from amaranth.sim import Simulator
from girlvoice.dsp.tdm_slice import TDMMultiply
from girlvoice.stream import stream_get, stream_put
from girlvoice.dsp.utils import generate_chirp


'''
An Envelope follower is essentially a special kind of low-pass filter
Its purpose is to trace the "envelope" of a signal. In a channel vocoder, this "envelope"
can be used to vary the amplification of one of the carrier signals.

This filter is implemented as an IIR low-pass filter with parameterized options for attack and decay
Largely inspired by the implementation described here:
https://kferg.dev/posts/2020/audio-reactive-programming-envelope-followers

Attack and decay input parameters represent the time to decay halfway (halflife) in milliseconds

'''
class EnvelopeFollower(wiring.Component):

    def __init__(self, sample_width=24, fs=48000, attack_halflife=10, decay_halflife=20, mult_slice:TDMMultiply = None):
        self.sample_width = sample_width
        self.fraction_width = sample_width - 1

        attack_hl_samples = fs * attack_halflife / 1000.0
        attack = math.exp(math.log(0.5) / attack_hl_samples)

        decay_hl_samples = fs * decay_halflife / 1000.0
        decay = math.exp(math.log(0.5) / decay_hl_samples)

        print(f"Envelope Decay parameter: {decay}")
        print(f"Envelope Attack parameter: {attack}")

        self.attack_fp = C(int(attack * (2**(self.fraction_width))), signed(sample_width))
        self.attack_comp = C(int((1 - attack) * (2**(self.fraction_width))), signed(sample_width))

        self.decay_fp = C(int(decay * (2**(self.fraction_width))), signed(sample_width))
        self.decay_comp = C(int((1 - decay) * (2**(self.fraction_width))), signed(sample_width))

        if mult_slice is not None:
            assert mult_slice.sample_width >= self.sample_width
            self.mult = mult_slice
        else:
            self.mult = None

        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })

    def elaborate(self, platform):
        m = Module()

        mac_width = self.sample_width*2
        acc = Signal(signed(mac_width))
        acc_quant = Signal(signed(self.sample_width))
        x = Signal(signed(self.sample_width))
        y = Signal(signed(self.sample_width))

        param = Signal(signed(self.sample_width))
        param_comp = Signal(signed(self.sample_width))
        m.d.comb += param.eq(Mux(abs(x) > y, self.attack_fp, self.decay_fp))
        m.d.comb += param_comp.eq(Mux(abs(x) > y, self.attack_comp, self.decay_comp))

        m.d.comb += x.eq(self.sink.payload)

        if self.mult is None:
            # acc.attrs["syn_multstyle"] = "block_mult"

            mac_out = Signal(signed(mac_width))
            mac_in_1 = Signal(signed(self.sample_width))
            mac_in_2 = Signal(signed(self.sample_width))
            m.d.comb += mac_out.eq(acc + (mac_in_1 * mac_in_2))
            # m.d.sync += Assert(acc >= 0, "Envelope accumulator overflow")
            m.d.comb += acc_quant.eq((mac_out) >> (self.fraction_width))

            with m.FSM():
                with m.State("LOAD"):
                    m.d.comb += self.source.valid.eq(0)
                    m.d.comb += self.sink.ready.eq(1)
                    with m.If(self.sink.valid):
                        m.d.sync += acc.eq(0)
                        m.d.sync += mac_in_1.eq(param_comp)
                        m.d.sync += mac_in_2.eq(abs(x))
                        m.next = "MULT_Y"
                with m.State("MULT_Y"):
                    m.d.sync += acc.eq(mac_out)
                    m.d.sync += mac_in_1.eq(param)
                    m.d.sync += mac_in_2.eq(y)
                    m.next = "READY"
                with m.State("READY"):
                    m.d.comb += self.source.valid.eq(1)
                    # Saturation logic:
                    with m.If(acc_quant >= 0):
                        m.d.comb += self.source.payload.eq(acc_quant)
                    with m.Else():
                        m.d.comb += self.source.payload.eq(2**(self.sample_width - 1) - 1)
                    with m.If(self.source.ready):
                        m.d.sync += y.eq(self.source.payload)
                        # m.d.sync += Assert(self.source.payload >= 0, "Envelope follower gave negative output")
                        m.next = "LOAD"

        else:

            mac_out = self.mult.source
            mac_in_1, mac_in_2, mult_valid = self.mult.get_next_thread_ports()

            m.d.comb += acc_quant.eq(acc >> self.fraction_width)

            m.d.comb += self.source.payload.eq(acc_quant)
            with m.If(self.sink.valid & self.sink.ready):
                m.d.sync += mac_in_1.eq(param_comp)
                m.d.sync += mac_in_2.eq(abs(x))
            with m.If(self.source.valid & self.source.ready):
                m.d.sync += self.source.valid.eq(0)
                m.d.sync += y.eq(self.source.payload)

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
    num_samples = duration * fs
    t = np.linspace(0, duration, num_samples)
    input_samples = signal.sawtooth(2 * np.pi * freq * t) * t
    input_samples *= (2**(sample_width - 1))
    input_samples = np.flip(input_samples)
    input_samples[0:int(0.1*num_samples)] = 0
    return (t, input_samples)

def run_sim():
    clk_freq = 60e6
    bit_width = 16
    fs = 48000
    mult = TDMMultiply(bit_width, num_threads=2)
    dut = EnvelopeFollower(sample_width=bit_width, fs=fs, mult_slice=mult)

    duration = 1
    start_freq = 1
    end_freq = 23000
    test_sig_freq = 5000
    (t, input_samples) = generate_ramp(test_sig_freq, duration, fs, bit_width)
    # (t, input_samples) = generate_chirp(duration, fs, start_freq, end_freq, bit_width)

    output_samples = []
    async def tb(ctx):
        samples_processed = 0
        for sample in input_samples:
            await stream_put(ctx, dut.sink, int(sample))
            output_samples.append(await stream_get(ctx, dut.source))
            await ctx.tick()
            samples_processed += 1
            if samples_processed % 1000 == 0:
                print(f"{samples_processed}/{len(t)} Samples processed")

    sim = Simulator(dut)
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        # bode_plot(fs, duration, end_freq, input_samples, output_samples)
        ax2 = plt.subplot(111)
        ax2.plot(t, input_samples, alpha=0.5, label="Input")
        ax2.plot(t, output_samples, alpha=0.5, label="Output")
        ax2.set_xlabel('time (s)')
        plt.title('Envelope Follower')
        plt.grid(True)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
        plt.legend()
        # plt.savefig(f"{type(dut).__name__}.png")
        plt.show()




if __name__ == "__main__":
    run_sim()