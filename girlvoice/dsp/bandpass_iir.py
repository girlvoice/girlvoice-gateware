#!/usr/bin/env python3
from math import ceil, log2
import os
import numpy as np
import matplotlib.pyplot as plt
from scipy import signal
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream
from girlvoice.dsp.tdm_slice import TDMMultiply

"""
IIR Bandpass filter using a Direct From I implementation
This module uses fixed point representation for sample data and filter coefficients
Incoming and outgoing samples are treated as Q(N-1) format where N is the bit width of the samples
The fixed point format for filter coefficients is determined on the fly by calculating how many
    integer bits are needed for the largest/smallest coeff

If M is the number of coefficient fraction bits then the result of multiplication of a coefficient and sample is Q(M+N-1)
To quantize the accumulator back to N-1 fraction bits we must divide by 2**((M+N-1) - (N-1)) = 2**M
This is achieved by adding 2**(M-1) to the accumulator and then right shifting by M bits
"""
class BandpassIIR(wiring.Component):
    def __init__(self, band_edges = None, center_freq = None, passband_width = None,
                 filter_order=2, sample_width=32, fs=48e3, mult_slice:TDMMultiply =None,
                 formal=False):
        self.order = filter_order
        self.sample_width = sample_width
        self.fs = fs
        self.formal=formal

        if mult_slice is not None:
            assert mult_slice.sample_width >= self.sample_width
        self.mult = mult_slice

        if band_edges is not None:
            band_edges = band_edges
        elif center_freq is not None and passband_width is not None:
            band_edges = [center_freq - passband_width/2, center_freq + passband_width / 2]
        else:
            raise ValueError("Must provide the bandpass filter width as band_edges or as center_freq and passband_width")

        print(f"Band edges: {band_edges}")
        btype = "bandpass"
        if band_edges[0] < 0:
            band_edges = band_edges[1]
            btype = "lowpass"
        b, a = signal.butter(N=filter_order, btype=btype, analog=False, fs=fs, output="ba", Wn=band_edges)

        self.taps_raw = [b, a]
        print(f"Numerator coeffs {b}")
        print(f"Denom: {a}")

        max_tap = np.max(np.abs(np.concatenate([b, a])))
        self.int_width = ceil(log2(max_tap) + 1)

        self.fraction_width = sample_width - self.int_width - 1

        print(f"Using {self.fraction_width} fraction bits and {self.int_width} integer bits")

        acc_frac = self.fraction_width * 2

        # The first coefficient for the denominator will always be 1.
        # In practice this means that we dont ever do anything with the first sample in the
        # feedback delay line. So we drop the first coefficient here and save a register in the delay line
        self.a_fp = Array([C(int(a_i * 2**self.fraction_width), signed(sample_width)) for a_i in a[1:]])
        self.b_fp = Array([C(int(b_i * 2**self.fraction_width), signed(sample_width)) for b_i in b])

        self.a_quant = [a.value / (2**self.fraction_width) for a in self.a_fp]
        self.b_quant = [b.value / (2**self.fraction_width) for b in self.b_fp]

        print(f"Numerator quantized: {self.b_quant}")
        print(f"Denom quantized: {self.a_quant}")
        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })


    def elaborate(self, platform):
        m = Module()

        self.multithreaded_mult = self.mult is not None

        num_taps = len(self.b_fp)

        # Direct form I implementation
        x_buf = Array([Signal(signed(self.sample_width), name=f"x_{i}") for i in range(len(self.b_fp))])
        y_buf = Array([Signal(signed(self.sample_width), name=f"y_{i}") for i in range(len(self.a_fp))])
        idx = Signal(range(num_taps))

        x_i = Signal(signed(self.sample_width))
        y_i = Signal(signed(self.sample_width))
        a_i = Signal(signed(self.sample_width))
        b_i = Signal(signed(self.sample_width))

        m.d.comb += x_i.eq(x_buf[idx])
        m.d.comb += y_i.eq(y_buf[idx])
        m.d.comb += a_i.eq(self.a_fp[idx])
        m.d.comb += b_i.eq(self.b_fp[idx])

        acc_width = (self.sample_width * 2) + (num_taps * 2)
        acc = Signal(signed(acc_width))
        self.acc_round = acc_round = Signal(signed(acc_width))
        m.d.comb += acc_round.eq(acc + 2**(self.fraction_width-1))

        if self.multithreaded_mult is not None:
            mult_node = self.mult.source
            mac_i_1, mac_i_2, mult_valid = self.mult.get_next_thread_ports()

            m.d.comb += self.source.payload.eq(acc_round >> (self.fraction_width))

            with m.If(self.source.ready & self.source.valid):
                m.d.sync += idx.eq(0)
            with m.FSM() as fsm:
                with m.State("LOAD"):
                    m.d.comb += self.sink.ready.eq(1)
                    with m.If(self.sink.valid):
                        m.d.sync += [x_buf[i + 1].eq(x_buf[i]) for i in range(num_taps - 1)]
                        m.d.sync += x_buf[0].eq(self.sink.payload)
                        m.d.sync += acc.eq(0)
                        m.next = "MAC_FEEDBACK"
                with m.State("MAC_FORWARD"):
                    with m.If(mult_valid):
                        m.d.sync += acc.eq(acc + mult_node)
                        m.d.sync += mac_i_1.eq(-y_i)
                        m.d.sync += mac_i_2.eq(a_i)
                        m.d.sync += idx.eq(idx + 1)
                        m.next = "MAC_FEEDBACK"
                        with m.If(idx == (num_taps - 1)):
                            m.next = "READY"

                with m.State("MAC_FEEDBACK"):
                    with m.If(mult_valid):
                        m.d.sync += mac_i_1.eq(x_i)
                        m.d.sync += mac_i_2.eq(b_i)
                        m.d.sync += acc.eq(acc + mult_node)
                        m.next = "MAC_FORWARD"

                with m.State("READY"):
                    m.d.comb += self.source.valid.eq(1)
                    with m.If(self.source.ready):
                        m.d.sync += [y_buf[i + 1].eq(y_buf[i]) for i in range(len(y_buf) - 1)]
                        m.d.sync += y_buf[0].eq(self.source.payload)
                        m.next = "LOAD"
            # self.fsm = fsm
        else:
            mult_node = Signal(signed(acc_width))
            mac_i_1 = Signal(signed(self.sample_width))
            mac_i_2 = Signal(signed(self.sample_width))

            m.d.comb += mult_node.eq(mac_i_1 * mac_i_2)

            with m.FSM() as fsm:
                with m.State("LOAD"):
                    m.d.comb += self.sink.ready.eq(1)
                    with m.If(self.sink.valid):
                        m.d.sync += [x_buf[i + 1].eq(x_buf[i]) for i in range(num_taps - 1)]
                        m.d.sync += [y_buf[i + 1].eq(y_buf[i]) for i in range(num_taps - 1)]
                        m.d.sync += x_buf[0].eq(self.sink.payload)
                        m.d.sync += acc.eq(0)
                        m.d.sync += idx.eq(idx + 1)
                        m.d.sync += mac_i_1.eq(self.sink.payload)
                        m.d.sync += mac_i_2.eq(b_i)
                        m.next = "MAC_FORWARD"

                with m.State("MAC_FORWARD"):
                    m.d.sync += acc.eq(acc + mult_node)

                    m.d.sync += mac_i_1.eq(-y_i)
                    m.d.sync += mac_i_2.eq(a_i)
                    m.next = "MAC_FEEDBACK"
                    with m.If(idx == num_taps):
                        m.next = "READY"

                with m.State("MAC_FEEDBACK"):
                    m.d.sync += mac_i_1.eq(x_i)
                    m.d.sync += mac_i_2.eq(b_i)
                    m.d.sync += idx.eq(idx + 1)
                    m.d.sync += acc.eq(acc + mult_node)
                    m.next = "MAC_FORWARD"

                with m.State("READY"):
                    m.d.comb += self.source.payload.eq(acc_round >> (self.fraction_width))
                    m.d.comb += self.source.valid.eq(1)
                    with m.If(self.source.ready):
                        m.d.sync += idx.eq(0)
                        m.d.sync += y_buf[0].eq(self.source.payload)
                        m.next = "LOAD"
            # self.fsm = fsm

        self.fsm = fsm

        if self.formal:
            self.add_asserts(m)
        return m

    def add_asserts(self, m):
        with m.If(self.fsm.ongoing("READY") & self.source.ready):
            m.d.sync += Assert(
                ((self.source.payload >= 0) & (self.acc_round >= 0))
                | ((self.source.payload < 0) & (self.acc_round < 0)),
                "IIR Bandpass Accumulator and output sign mismatch!")

# Testbench ----------------------------------------

def run_sim():
    from amaranth.sim import Simulator
    from girlvoice.stream import stream_get, stream_put
    from girlvoice.dsp.utils import generate_chirp, bode_plot

    clk_freq = 60e6
    sample_width = 16 # Number of 2s complement bits
    fs = 48000
    m = Module()
    m.submodules.mult = mult = TDMMultiply(sample_width=sample_width, num_threads=3)
    m.submodules.filt = dut = BandpassIIR(
        center_freq=5000,
        passband_width=1000,
        fs=fs,
        sample_width=sample_width,
        filter_order=1,
        mult_slice=mult
    )


    duration = .25
    start_freq = 1
    end_freq = fs / 2
    (t, input_samples) = generate_chirp(duration, fs, start_freq, end_freq, sample_width, amp=1)
    input_samples
    output_samples = np.zeros(int(duration * fs))
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


    sim = Simulator(m)
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        print(output_samples[-50:])
        ax2 = plt.subplot(121)
        dut_a = dut.a_quant.copy() # The implicit 1 coefficient is removed to save LUTS, add it back in here
        dut_a.insert(0, 1.0)
        bode_plot(fs, duration, end_freq, input_samples, output_samples, dut.taps_raw, [dut.b_quant, dut_a])
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