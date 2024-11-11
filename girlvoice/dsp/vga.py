import numpy as np
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream

class VariableGainAmp(wiring.Component):
    def __init__(self, carrier_width, modulator_width):
        self.modulator_width = modulator_width
        self.carrier_width = carrier_width
        super().__init__({
            "carrier": In(stream.Signature(signed(carrier_width))),
            "modulator": In(stream.Signature(signed(modulator_width))),
            "source": Out(stream.Signature(signed(carrier_width)))
        })

    def elaborate(self, platform):
        m = Module()

        i_valid = Signal()

        product = Signal(signed(self.carrier_width + self.modulator_width))
        # product.attrs["syn_multstyle"] = "block_mult"

        m.d.comb += product.eq(self.carrier.payload * self.modulator.payload)
        m.d.comb += i_valid.eq(self.modulator.valid & self.carrier.valid)

        with m.If(i_valid & (~self.source.valid | self.source.ready)):
            m.d.sync += self.source.payload.eq(product >> (self.modulator_width - 1))
            m.d.sync += self.source.valid.eq(1)
            m.d.comb += self.carrier.ready.eq(1)
            m.d.comb += self.modulator.ready.eq(1)
        with m.Elif(self.source.ready):
            m.d.sync += self.source.valid.eq(0)

        return m