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
from girlvoice.stream import stream_get, stream_put


'''
Combined Envelope follower and VGA. Saves a multiplication by combining the two components
'''
class EnvelopeVGA(wiring.Component):

    def __init__(self, sample_width=24, fs=48000, attack_halflife=10, decay_halflife=20):
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

        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "carrier": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })

    def elaborate(self, platform):
        m = Module()

        mac_width = self.sample_width*2
        acc = Signal(signed(mac_width))
        acc_quant = Signal(signed(self.sample_width))

        mult_node = Signal(signed(mac_width))
        mac_in_1 = Signal(signed(self.sample_width))
        mac_in_2 = Signal(signed(self.sample_width))
        m.d.comb += mult_node.eq(mac_in_1 * mac_in_2)
        # m.d.sync += Assert(acc >= 0, "Envelope accumulator overflow")
        m.d.comb += acc_quant.eq(mult_node >> (self.fraction_width))

        x = Signal(signed(self.sample_width))
        y = Signal(signed(self.sample_width))

        param = Signal(signed(self.sample_width))
        param_comp = Signal(signed(self.sample_width))
        m.d.comb += param.eq(Mux(abs(x) > y, self.attack_fp, self.decay_fp))
        m.d.comb += param_comp.eq(Mux(abs(x) > y, self.attack_comp, self.decay_comp))

        m.d.comb += x.eq(self.sink.payload)

        # Saturation logic:
        with m.If(acc_quant >= 0):
            m.d.comb += self.source.payload.eq(acc_quant)
        with m.Else():
            m.d.comb += self.source.payload.eq(2**(self.sample_width - 1) - 1)

        with m.FSM():
            with m.State("LOAD"):
                # m.d.comb += self.source.valid.eq(0)
                m.d.comb += self.sink.ready.eq(1)
                with m.If(self.sink.valid):
                    m.d.sync += acc.eq(0)
                    m.d.sync += mac_in_1.eq(param_comp)
                    m.d.sync += mac_in_2.eq(abs(x))
                    m.next = "MULT_Y"

            with m.State("MULT_Y"):
                m.d.sync += acc.eq(mult_node)
                m.d.sync += mac_in_1.eq(param)
                m.d.sync += mac_in_2.eq(y)
                m.next = "ACC_Y"

            with m.State("ACC_Y"):
                m.d.sync += acc.eq(acc + mult_node)
                m.d.sync += self.carrier.ready.eq(1)
                m.next = "MULT_CARRIER"

            # ACC reg now contains the output of the envelope follower
            with m.State("MULT_CARRIER"):
                m.d.sync += mac_in_1.eq(acc_quant)
                with m.If(self.carrier.valid):
                    m.d.sync += mac_in_2.eq(self.carrier.payload)
                    m.d.sync += self.carrier.ready.eq(0)
                    m.d.sync += self.source.valid.eq(1)
                    m.next = "READY"

            with m.State("READY"):
                with m.If(self.source.ready):
                    m.d.sync += y.eq(self.source.payload)
                    m.d.sync += self.source.valid.eq(0)
                    # m.d.sync += Assert(self.source.payload >= 0, "Envelope follower gave negative output")
                    m.next = "LOAD"
        return m
