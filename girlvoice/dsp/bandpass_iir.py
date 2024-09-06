#!/usr/bin/env python3
from numpy import sign
from scipy import signal
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream

from amaranth.sim import Simulator


class BandpassIIR(wiring.Component):
    def __init__(self, cutoff_freq, passband_width, filter_order=24, sample_width=32, samplerate=48e3):
        self.order = filter_order
        self.sample_width = sample_width
        self.fs = samplerate
        self.fraction_width = sample_width - 2

        a, b = signal.iirfilter(N=filter_order, btype="bandpass", analog=False, fs=samplerate)

        self.a_fp = [C(int(a_i * 2**self.fraction_width), signed(sample_width)) for a_i in a]
        self.b_fp = [C(int(b_i * 2**self.fraction_width), signed(sample_width)) for b_i in b]

        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })


    def elaborate(self, platform):
        m = Module()

        num_taps = self.order + 1

        # Direct form I implementation
        x_buf = Array([Signal(signed(self.sample_width)) for _ in range(len(self.b_fp))])
        y_buf = Array([Signal(signed(self.sample_width)) for _ in range(len(self.a_fp))])
        idx = Signal(range(len(num_taps)))

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
                m.d.sync += self.source.valid.eq(0)
                with m.If(self.sink.valid):
                    m.d.sync += [x_buf[i + 1].eq(x_buf[i]) for i in range(num_taps - 1)]
                    m.d.sync += [y_buf[i + 1].eq(y_buf[i]) for i in range(num_taps - 1)]
                    m.d.sync += x_buf[0].eq(self.sink.payload)
                    m.d.sync += acc.eq(0)
                    m.d.sync += idx.eq(0)

            with m.State("MAC_FORWARD"):
                m.d.sync += acc.eq(acc + (x_i * b_i))
                m.d.sync += idx.eq(idx + 1)
                m.next = "MAC_FEEDBACK"
                with m.If(idx == len(self.taps) - 1):
                    m.d.sync += self.source.payload.eq(acc >> (len(acc) - self.sample_width))

            with m.State("MAC_FEEDBACK"):
                m.d.sync += acc.eq(acc + (y_i * a_i))
                m.next = "MAC_FEEDBACK"

            with m.State("READY"):
                m.d.comb += self.source.valid.eq(1)
                with m.If(self.source.ready):
                    m.d.sync += y_buf[0].eq(self.source.payload)
                    m.next = "LOAD"

        return m
