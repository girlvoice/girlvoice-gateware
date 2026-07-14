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
from amaranth.lib import memory
from typing import List, Tuple

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


class BandpassIIREngine(wiring.Component):
    def __init__(
        self,
        num_instances: int,
        band_edges: List[Tuple[float, float]] =None,
        center_freq: List[float] =None,
        passband_width: List[float] =None,
        filter_order=1,
        sample_width=32,
        fs=48e3,
        formal=False,
    ):
        self.order = filter_order
        self.num_taps = 1 + (filter_order * 2)
        self.sample_width = sample_width
        self.fs = fs
        self.formal = formal
        self.instances = num_instances

        if band_edges is not None:
            band_edges = band_edges
        elif center_freq is not None and passband_width is not None:
            band_edges = []
            for i in range(num_instances):
                inst_band_edges = [
                    center_freq[i] - passband_width[i] / 2,
                    center_freq[i] + passband_width[i] / 2,
                ]
                band_edges.append(inst_band_edges)

        else:
            raise ValueError(
                "Must provide the bandpass filter width as band_edges or as center_freq and passband_width"
            )

        # list of coefficients for each instance.
        # a_coeffs[i] contains the coefficients for the ith filter
        a_coeffs = []
        b_coeffs = []

        # same as above but for the fixed-point representations of the coefficients
        a_coeffs_fp = []
        b_coeffs_fp = []
        self.taps_raw = []

        self.fraction_width = self.sample_width - 1
        for inst_i in range(num_instances):
            print(f"Band edges: {band_edges}")
            btype = "bandpass"
            inst_band_edges = band_edges[inst_i]
            if inst_band_edges[0] < 0:
                inst_band_edges = band_edges[1]
                btype = "lowpass"
            b, a = signal.butter(
                N=filter_order, btype=btype, analog=False, fs=fs, output="ba", Wn=inst_band_edges
            )

            self.taps_raw.append([b, a])
            print(f"Numerator coeffs {b}")
            print(f"Denom: {a}")

            a_coeffs.append(a)
            b_coeffs.append(b)

            max_tap = np.max(np.abs(np.concatenate([b, a])))
            self.int_width = ceil(log2(max_tap) + 1)

            # if self.fraction_width is not None and self.fraction_width != (sample_width - self.int_width - 1):
            #     raise ValueError(f"mismatched coefficient fraction bit length, current frac width: {self.fraction_width} new frac width: {(sample_width - self.int_width - 1)}")
            self.fraction_width = min(self.fraction_width, sample_width - self.int_width - 1)

            print(
                f"Using {self.fraction_width} fraction bits and {self.int_width} integer bits"
            )

        # Conversion to fixed point needs to happen after all coefficients have been generated
        # This ensures that we have found the maximum number of integer bits needed for all coefficients
        for i in range(num_instances):
            a = a_coeffs[i]
            b = b_coeffs[i]
            # The first coefficient for the denominator will always be 1.
            # In practice this means that we dont ever do anything with the first sample in the
            # feedback delay line. So we drop the first coefficient here and save a register in the delay line
            a_coeffs_fp.append([ int(a_i * 2**self.fraction_width) for a_i in a[1:] ])
            b_coeffs_fp.append([ int(b_i * 2**self.fraction_width) for b_i in b ])

        print (b_coeffs_fp)
        # Memories for per-instance filter coefficients
        self.a_mems = []
        self.a_rd_ports = []
        for i in range(self.num_taps - 1):
            a_i_mem = memory.Memory(
                shape=signed(self.sample_width),
                depth=self.instances,
                init=[ a_coeffs_fp[inst][i] for inst in range(num_instances) ]
            )
            self.a_mems.append(a_i_mem)
            self.a_rd_ports.append(a_i_mem.read_port())

        self.b_mems = []
        self.b_rd_ports = []
        for i in range(self.num_taps):
            b_i_mem = memory.Memory(
                shape=signed(self.sample_width),
                depth=self.instances,
                init=[ b_coeffs_fp[inst][i] for inst in range(num_instances) ]
            )
            self.b_mems.append(b_i_mem)
            self.b_rd_ports.append(b_i_mem.read_port())


        # Index-able arrays of signals for
        # easy access to coefficients of the filter currently being processed
        self.a_fp = Array(
            [ self.a_rd_ports[i].data for i in range(self.num_taps - 1) ]
        )
        self.b_fp = Array(
            [ self.b_rd_ports[i].data for i in range(self.num_taps) ]
        )

        # For debug output of parameter values
        self.a_quant = [ [a / (2**self.fraction_width) for a in a_coeffs_fp[inst]] for inst in range(num_instances) ]
        self.b_quant = [[b / (2**self.fraction_width) for b in b_coeffs_fp[inst]] for inst in range(num_instances)]

        print(f"Numerator quantized: {self.b_quant}")
        print(f"Denom quantized: {self.a_quant}")

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

        num_taps = self.num_taps

        # Index of current filter instance to process
        cur_inst = Signal(range(self.instances))
        cur_inst_read_pointer = Signal(range(self.instances))


        # Memories for storing delayed feedback samples
        y_mems = []
        y_rd_ports = []
        y_wr_ports = []
        y_wr_en = Signal()
        for tap_i in range(len(self.a_fp)):
            m.submodules[f"y_{tap_i + 1}_mem"] = y_i_mem =  memory.Memory(
                shape=signed(self.sample_width),
                depth=self.instances,
                init=[0] * self.instances
            )
            y_mems.append(y_i_mem)
            rd_port = y_i_mem.read_port()
            wr_port = y_i_mem.write_port()
            y_rd_ports.append(rd_port)
            y_wr_ports.append(wr_port)

            a_i_rd_port = self.a_rd_ports[tap_i]
            m.d.comb += [
                rd_port.en.eq(1),
                a_i_rd_port.en.eq(1),
                rd_port.addr.eq(cur_inst),
                a_i_rd_port.addr.eq(cur_inst_read_pointer),
                wr_port.addr.eq(cur_inst),
                wr_port.en.eq(y_wr_en),
            ]

            m.submodules[f"a_{tap_i + 1}_mem"] = self.a_mems[tap_i]

        for tap_i in range(num_taps):
            m.submodules[f"b_{tap_i}_mem"] = self.b_mems[tap_i]
            b_i_rd_port = self.b_rd_ports[tap_i]
            m.d.comb += b_i_rd_port.en.eq(1)
            m.d.comb += b_i_rd_port.addr.eq(cur_inst_read_pointer)


        # Direct form I implementation
        x_buf = Array(
            [Signal(signed(self.sample_width), name=f"x_{i}") for i in range(num_taps)]
        )
        y_rd_buf = Array([ y_rd_ports[i].data for i in range(num_taps - 1) ])
        y_wr_buf = Array([ y_wr_ports[i].data for i in range(num_taps - 1) ])

        idx = Signal(range(num_taps))

        x_0 = Signal(signed(self.sample_width))
        y_0 = Signal(signed(self.sample_width))
        x_i = Signal(signed(self.sample_width))
        y_i = Signal(signed(self.sample_width))
        a_i = Signal(signed(self.sample_width))
        b_i = Signal(signed(self.sample_width))

        output_sample = Signal(signed(self.sample_width))

        m.d.comb += x_i.eq(x_buf[idx])
        m.d.comb += y_i.eq(y_rd_buf[idx])
        m.d.comb += a_i.eq(self.a_fp[idx])
        m.d.comb += b_i.eq(self.b_fp[idx])

        m.d.comb += y_wr_buf[0].eq(y_0)

        acc_width = (self.sample_width * 2) + (num_taps * 2)
        acc = Signal(signed(acc_width))
        self.acc_round = acc_round = Signal(signed(acc_width))
        # m.d.comb += acc_round.eq(acc + 2**(self.fraction_width-1))
        m.d.comb += acc_round.eq(acc)
        m.d.comb += output_sample.eq(acc_round >> self.fraction_width)


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
        m.d.comb += x_0.eq(sink_vector.word_select(cur_inst, self.sample_width))

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

        mult_node = Signal(signed(acc_width))
        mac_i_1 = Signal(signed(self.sample_width))
        mac_i_2 = Signal(signed(self.sample_width))

        m.d.comb += mult_node.eq(mac_i_1 * mac_i_2)

        with m.FSM() as fsm:
            with m.State("LOAD"):
                m.d.comb += input_sample_ready.eq(1)
                with m.If(cur_sink_valid):
                    with m.If(cur_inst == 0):
                        m.d.sync += [
                            x_buf[i + 1].eq(x_buf[i]) for i in range(num_taps - 1)
                        ]
                    m.d.sync += x_buf[0].eq(x_0)
                    m.d.sync += acc.eq(0)
                    # m.d.sync += idx.eq(idx + 1)
                    m.d.sync += mac_i_1.eq(x_0)
                    m.d.sync += mac_i_2.eq(b_i)
                    m.d.sync += input_ready_mask.eq(input_ready_mask.rotate_left(1))
                    m.next = "MAC_FORWARD"

            with m.State("MAC_FORWARD"):
                m.d.sync += y_wr_en.eq(0)
                m.d.sync += acc.eq(acc + mult_node)
                m.d.sync += idx.eq(idx + 1)

                m.d.sync += mac_i_1.eq(-y_i)
                m.d.sync += mac_i_2.eq(a_i)
                m.next = "MAC_FEEDBACK"
                with m.If(idx == num_taps - 1):
                    m.d.sync += y_wr_en.eq(1)
                    m.d.sync += [
                        y_wr_buf[i + 1].eq(y_rd_buf[i]) for i in range(len(y_wr_buf) - 1)
                    ]
                    with m.If(cur_inst_read_pointer != (self.instances - 1)):
                        m.d.sync += cur_inst_read_pointer.eq(cur_inst_read_pointer + 1)
                    with m.Else():
                        m.d.sync += cur_inst_read_pointer.eq(0)
                    m.next = "READY"

            with m.State("MAC_FEEDBACK"):
                m.d.sync += mac_i_1.eq(x_i)
                m.d.sync += mac_i_2.eq(b_i)
                m.d.sync += acc.eq(acc + mult_node)
                m.next = "MAC_FORWARD"

            with m.State("READY"):
                m.d.comb += output_sample_valid.eq(1)
                m.d.sync += y_wr_en.eq(0)
                m.d.comb += y_0.eq(output_sample)
                with m.If(cur_source_ready):
                    m.d.sync += idx.eq(0)
                    m.d.sync += output_valid_mask.eq(output_valid_mask.rotate_left(1))
                    with m.If(cur_inst != (self.instances - 1)):
                        m.d.sync += cur_inst.eq(cur_inst + 1)
                    with m.Else():
                        m.d.sync += cur_inst.eq(0)
                    m.next = "LOAD"

        self.fsm = fsm


        if self.formal:
            with m.If(self.fsm.ongoing("READY") & cur_source_ready):
                m.d.sync += Assert(
                    ((output_sample >= 0) & (self.acc_round >= 0))
                    | ((output_sample < 0) & (self.acc_round < 0)),
                    "IIR Bandpass Accumulator and output sign mismatch!",
                )
        return m



# Testbench ----------------------------------------


def run_sim():
    from amaranth.sim import Simulator
    from girlvoice.stream import stream_get, stream_put
    from girlvoice.dsp.utils import generate_chirp, bode_plot

    clk_freq = 60e6
    sample_width = 16  # Number of 2s complement bits
    fs = 48000
    num_inst = 4
    m = Module()
    m.submodules.filt = dut = BandpassIIREngine(
        center_freq=[5000, 10000, 1000, 16000],
        passband_width=[500, 100, 200, 1000],
        # center_freq=[10000, 5000],
        # passband_width=[100, 500],
        num_instances=num_inst,
        fs=fs,
        sample_width=sample_width,
        filter_order=1,
        formal=True,
    )

    duration = 0.25
    start_freq = 1
    end_freq = fs / 2
    (t, input_samples) = generate_chirp(
        duration, fs, start_freq, end_freq, sample_width, amp=1
    )
    # output_samples = np.zeros(int(duration * fs))
    output_samples = [[] for _ in range(num_inst) ]

    async def tb(ctx):
        samples_processed = 0
        await ctx.tick()
        for sample in input_samples:
            for i in range(num_inst):
                await stream_put(ctx, dut.sink(i), int(sample))
                output_samples[i].append(await stream_get(ctx, dut.source(i)))
            await ctx.tick()
            samples_processed += 1
            if samples_processed % 1000 == 0:
                print(f"{samples_processed}/{len(t)} Samples processed")

    sim = Simulator(m)
    sim.add_clock(1 / clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        ax2 = plt.subplot(121)
        for i in range(num_inst):

            dut_a = (
                dut.a_quant[i].copy()
            )  # The implicit 1 coefficient is removed to save LUTS, add it back in here
            dut_a.insert(0, 1.0)
            bode_plot(
                fs,
                duration,
                end_freq,
                input_samples,
                output_samples[i],
                dut.taps_raw[i],
                [dut.b_quant[i], dut_a],
                suffix = i,
            )
        ax2.plot(t, input_samples, alpha=0.5, label="Input")
        for i in range(num_inst):
            ax2.plot(t, output_samples[i], alpha=0.5, label=f"Output_{i}")
        ax2.set_xlabel("Time (s)")
        ax2.set_ylabel("Amplitude")
        plt.title("Bandpass IIR")
        plt.grid(True)
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", borderaxespad=0.0)
        plt.legend()
        # plt.savefig(f"{type(dut).__name__}.png")
        plt.show()


if __name__ == "__main__":
    run_sim()
