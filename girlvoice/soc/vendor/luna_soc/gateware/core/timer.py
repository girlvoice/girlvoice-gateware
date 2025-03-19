#
# This file is part of LUNA.
#
# Copyright (c) 2020-2025 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

""" A simple timer peripheral. """

from amaranth             import *
from amaranth.lib         import enum, wiring
from amaranth.lib.wiring  import In, Out, flipped, connect

from amaranth_soc         import csr, event


class Peripheral(wiring.Component):
    class Enable(csr.Register, access="rw"):
        """Counter enable"""
        enable: csr.Field(csr.action.RW, unsigned(1))

    class Mode(csr.Register, access="rw"):
        """Timer mode. When ``periodic`` is set to 1 the counter will automatically be reset to the reload value."""
        periodic: csr.Field(csr.action.RW, unsigned(1))

    class Reload(csr.Register, access="rw"):
        """Reload value of counter."""
        def __init__(self, width):
            super().__init__({
                "value": csr.Field(csr.action.RW, unsigned(width))
            })

    class Counter(csr.Register, access="r"):
        def __init__(self, width):
            """Counter value"""
            super().__init__({
                "value": csr.Field(csr.action.R, unsigned(width))
            })


    def __init__(self, *, width):
        if not isinstance(width, int) or width < 0:
            raise ValueError("Counter width must be a non-negative integer, not {!r}"
                             .format(width))
        if width > 32:
            raise ValueError("Counter width cannot be greater than 32 (was: {})"
                             .format(width))
        self.width   = width

        # registers
        regs = csr.Builder(addr_width=4, data_width=8)
        self._enable  = regs.add("enable",  self.Enable())
        self._mode    = regs.add("mode",    self.Mode())
        self._reload  = regs.add("reload",  self.Reload(width))
        self._counter = regs.add("counter", self.Counter(width))
        self._bridge = csr.Bridge(regs.as_memory_map())

        # events
        from typing import Annotated
        ResetSource = Annotated[event.Source, "Interrupt that occurs when the timer reaches zero."]
        self._zero = ResetSource(path=("zero",))
        event_map = event.EventMap()
        event_map.add(self._zero)
        self._events = csr.event.EventMonitor(event_map, data_width=8)

        # csr decoder
        self._decoder = csr.Decoder(addr_width=5, data_width=8)
        self._decoder.add(self._bridge.bus)
        self._decoder.add(self._events.bus, name="ev")

        super().__init__({
            "bus":    Out(self._decoder.bus.signature),
            "irq":    Out(unsigned(1)),
        })
        self.bus.memory_map = self._decoder.bus.memory_map

    def elaborate(self, platform):
        m = Module()
        m.submodules += [self._bridge, self._events, self._decoder]

        # connect bus
        connect(m, flipped(self.bus), self._decoder.bus)

        # peripheral logic
        zero = Signal()
        finish = Signal()
        with m.If(self._enable.f.enable.data):
            with m.If(self._counter.f.value.r_data == 0):
                m.d.comb += zero.eq(~finish)
                with m.If(self._mode.f.periodic.data):
                    m.d.sync += self._counter.f.value.r_data.eq(self._reload.f.value.data)
                with m.Else():
                    m.d.sync += finish.eq(1)
            with m.Else():
                m.d.sync += self._counter.f.value.r_data.eq(self._counter.f.value.r_data - 1)
        with m.Else():
            m.d.sync += self._counter.f.value.r_data.eq(self._reload.f.value.data)
            m.d.sync += finish.eq(0)

        # connect events to irq line
        m.d.comb += [
            self._zero.i  .eq(zero),
            self.irq      .eq(self._events.src.i),
        ]

        return m
