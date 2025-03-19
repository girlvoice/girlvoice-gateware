#
# This file is part of LUNA.
#
# Copyright (c) 2020-2025 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

from amaranth              import *
from amaranth.lib          import enum, wiring
from amaranth.lib.wiring   import In, Out, flipped, connect

from amaranth_soc          import csr, event


class Peripheral(wiring.Component):
    """ A simple peripheral interface to the ila. """
    class Control(csr.Register, access="w"):
        trigger: csr.Field(csr.action.W, unsigned(1))

    class Trace(csr.Register, access="w"):
        a: csr.Field(csr.action.W, unsigned(8))
        b: csr.Field(csr.action.W, unsigned(8))
        c: csr.Field(csr.action.W, unsigned(8))
        d: csr.Field(csr.action.W, unsigned(8))

    def __init__(self):
        # registers
        regs = csr.Builder(addr_width=4, data_width=8)
        self._control = regs.add("control", self.Control())
        self._trace   = regs.add("trace",   self.Trace())
        self._bridge = csr.Bridge(regs.as_memory_map())

        # csr decoder
        self._decoder = csr.Decoder(addr_width=5, data_width=8)
        self._decoder.add(self._bridge.bus)

        super().__init__({
            "bus":      Out(self._decoder.bus.signature),
            "trigger":  Out(unsigned(1)),
            "a":        Out(unsigned(8)),
            "b":        Out(unsigned(8)),
            "c":        Out(unsigned(8)),
            "d":        Out(unsigned(8)),
        })
        self.bus.memory_map = self._decoder.bus.memory_map

    def elaborate(self, platform):
        m = Module()
        m.submodules += [self._bridge, self._decoder]

        # connect bus
        connect(m, flipped(self.bus), self._decoder.bus)

        # logic
        with m.If(self._control.f.trigger.w_stb):
            m.d.comb += self.trigger .eq(self._control.f.trigger.w_data)
        with m.If(self._trace.f.a.w_stb):
            m.d.comb += self.a       .eq(self._trace.f.a.w_data)
        with m.If(self._trace.f.b.w_stb):
            m.d.comb += self.b       .eq(self._trace.f.b.w_data)
        with m.If(self._trace.f.c.w_stb):
            m.d.comb += self.c       .eq(self._trace.f.c.w_data)
        with m.If(self._trace.f.d.w_stb):
            m.d.comb += self.d       .eq(self._trace.f.d.w_data)

        return m
