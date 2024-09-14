#!/usr/bin/env python3
import os
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream

from amaranth.sim import Simulator

from girlvoice.stream import stream_get, stream_put
from girlvoice.dsp.utils import generate_chirp

class BandpassIIR(wiring.Component):
    def __init__(self, cutoff_freq, passband_width, filter_order=24, sample_width=32, samplerate=48e3):
        self.order = filter_order
        self.sample_width = sample_width
        self.fs = samplerate
        self.int_width = 3
        self.fraction_width = sample_width - self.int_width - 1


        band_edges = [cutoff_freq - passband_width/2, cutoff_freq + passband_width / 2]
        # a, b = signal.iirfilter(N=filter_order, btype="bandpass", analog=False, fs=samplerate, Wn=band_edges)
        b, a = signal.butter(N=filter_order, btype="bandpass", analog=False, fs=samplerate, output="ba", Wn=band_edges)
        print(f"Numerator coeffs {b}")
        print(f"Denom: {a}")
        self.a_fp = Array([C(int(a_i * 2**self.fraction_width), signed(sample_width)) for a_i in a])
        self.b_fp = Array([C(int(b_i * 2**self.fraction_width), signed(sample_width)) for b_i in b])



        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })


    def elaborate(self, platform):
        m = Module()

        num_taps = len(self.a_fp)

        # Direct form I implementation
        x_buf = Array([Signal(signed(self.sample_width)) for _ in range(len(self.b_fp))])
        y_buf = Array([Signal(signed(self.sample_width)) for _ in range(len(self.a_fp))])
        idx = Signal(range(num_taps))

        x_i = Signal(signed(self.sample_width))
        y_i = Signal(signed(self.sample_width))
        a_i = Signal(signed(self.sample_width))
        b_i = Signal(signed(self.sample_width))

        m.d.comb += x_i.eq(x_buf[idx])
        m.d.comb += y_i.eq(y_buf[idx])
        m.d.comb += a_i.eq(self.a_fp[idx])
        m.d.comb += b_i.eq(self.b_fp[idx])

        acc_width = self.sample_width * 2
        acc = Signal(signed(acc_width))

        with m.FSM():
            with m.State("LOAD"):
                m.d.comb += self.sink.ready.eq(1)
                # m.d.sync += self.source.valid.eq(0)
                with m.If(self.sink.valid):
                    m.d.sync += [x_buf[i + 1].eq(x_buf[i]) for i in range(num_taps - 1)]
                    m.d.sync += [y_buf[i + 1].eq(y_buf[i]) for i in range(num_taps - 1)]
                    m.d.sync += x_buf[0].eq(self.sink.payload)
                    m.d.sync += acc.eq(0)
                    m.d.sync += idx.eq(0)
                    m.next = "MAC_FORWARD"

            with m.State("MAC_FORWARD"):
                m.d.sync += acc.eq(acc + (x_i * b_i))
                m.d.sync += idx.eq(idx + 1)
                m.next = "MAC_FEEDBACK"
                with m.If(idx == num_taps - 1):
                    # m.d.sync += self.source.payload.eq(acc >> (self.sample_width))
                    m.next = "READY"

            with m.State("MAC_FEEDBACK"):
                m.d.sync += acc.eq(acc + (y_i * a_i))
                m.next = "MAC_FORWARD"

            with m.State("READY"):
                m.d.comb += self.source.payload.eq(acc >> (self.fraction_width))
                m.d.comb += self.source.valid.eq(1)
                with m.If(self.source.ready):
                    m.d.sync += y_buf[0].eq(self.source.payload)
                    m.next = "LOAD"

        return m

def run_sim():
    clk_freq = 60e6
    sample_width = 32 # Number of 2s complement bits
    fs = 32000
    dut = BandpassIIR(cutoff_freq=1000, passband_width=1000, samplerate=fs, sample_width=sample_width, filter_order=2)

    duration = 1
    start_freq = 1
    end_freq = 5000
    test_sig_freq = 5000
    (t, input_samples) = generate_chirp(duration, fs, start_freq, end_freq, sample_width)

    output_samples = np.zeros(duration * fs)
    async def tb(ctx):
        samples_processed = 0
        await ctx.tick()
        for sample in input_samples:
            await stream_put(ctx, dut.sink, int(sample))
            output_samples[samples_processed] = (await stream_get(ctx, dut.source))
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
        ax2 = plt.subplot(121)
        # bode_plot(fs, duration, end_freq, input_samples, output_samples, dut.taps_raw)
        ax2.plot(t, input_samples, alpha=0.5, label="Input")
        ax2.plot(t, output_samples, alpha=0.5, label="Output")
        ax2.set_xlabel('Time (s)')
        ax2.set_ylabel("Amplitude")
        plt.title('Bandpass IIR')
        plt.grid(True)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
        plt.legend()
        # plt.savefig(f"{type(dut).__name__}.png")
        plt.show()

if __name__ == "__main__":
    run_sim()