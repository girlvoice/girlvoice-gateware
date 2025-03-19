#
# This file is part of LUNA.
#
# Copyright (c) 2020-2024 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

"""
Contains the organizing gateware used to add USB Device functionality
to your own designs; including the core :class:`USBDevice` class.
"""

from typing                         import Annotated

from amaranth                       import *
from amaranth.lib                   import wiring
from amaranth.lib.wiring            import In, Out, connect, flipped

from amaranth_soc                   import csr, event

from luna.gateware.usb.usb2.device  import USBDevice


class Peripheral(wiring.Component):
    """ SoC controller for a USBDevice.

    Breaks our USBDevice control and status signals out into registers so a CPU / Wishbone master
    can control our USB device.

    The attributes below are intended to connect to a USBDevice. Typically, they'd be created by
    using the .controller() method on a USBDevice object, which will automatically connect all
    relevant signals.

    Attributes
    ----------

    connect: Signal(), output
        High when the USBDevice should be allowed to connect to a host.

    """

    class Control(csr.Register, access="rw"):
        """Control register

            connect:         Set this bit to '1' to allow the associated USB device to connect to a host.
            low_speed_only:  Set this bit to '1' to force the device to operate at low speed.
            full_speed_only: Set this bit to '1' to force the device to operate at full speed.
        """
        connect         : csr.Field(csr.action.RW,      unsigned(1))
        _0              : csr.Field(csr.action.ResRAW0, unsigned(7))
        low_speed_only  : csr.Field(csr.action.RW,      unsigned(1))
        full_speed_only : csr.Field(csr.action.RW,      unsigned(1))
        _1              : csr.Field(csr.action.ResRAW0, unsigned(6))

    class Status(csr.Register, access="r"):
        """Status register

            speed: Indicates the current speed of the USB device. 0 indicates High; 1 => Full,
                   2 => Low, and 3 => SuperSpeed (incl SuperSpeed+).
        """
        speed : csr.Field(csr.action.R,       unsigned(2))
        _0    : csr.Field(csr.action.ResRAW0, unsigned(6))

    def __init__(self):
        # I/O ports  FIXME ambiguity - private or signature ?
        self.connect         = Signal(init=1)
        self.bus_reset       = Signal()
        self.low_speed_only  = Signal()
        self.full_speed_only = Signal()

        # registers
        regs = csr.Builder(addr_width=3, data_width=8)
        self._control = regs.add("control", self.Control())
        self._status  = regs.add("status",  self.Status())
        self._bridge = csr.Bridge(regs.as_memory_map())

        # events
        EventSource = Annotated[event.Source, "Interrupt that occurs when a USB bus reset is received."]
        self._reset = EventSource(path=("reset",))
        event_map = event.EventMap()
        event_map.add(self._reset)
        self._events = csr.event.EventMonitor(event_map, data_width=8)

        # csr decoder
        self._decoder = csr.Decoder(addr_width=4, data_width=8)
        self._decoder.add(self._bridge.bus)
        self._decoder.add(self._events.bus, name="ev")

        super().__init__({
            "bus":    Out(self._decoder.bus.signature),
            "irq":    Out(unsigned(1)),
        })
        self.bus.memory_map = self._decoder.bus.memory_map


    def attach(self, device: USBDevice):
        """ Returns a list of statements necessary to connect this to a USB controller.

        The returned values makes all of the connections necessary to provide control and fetch status
        from the relevant USB device. These can be made either combinationally or synchronously, but
        combinational is recommended; as these signals are typically fed from a register anyway.

        Parameters
        ----------
        device: USBDevice
            The :class:`USBDevice` object to be controlled.
        """
        return [
            device.connect               .eq(self.connect),
            device.low_speed_only        .eq(self.low_speed_only),
            device.full_speed_only       .eq(self.full_speed_only),
            self.bus_reset               .eq(device.reset_detected),
            self._status.f.speed.r_data  .eq(device.speed)
        ]


    def elaborate(self, platform):
        m = Module()
        m.submodules += [self._bridge, self._events, self._decoder]

        # connect bus
        connect(m, flipped(self.bus), self._decoder.bus)

        # Core connection register.
        m.d.comb += self.connect.eq(self._control.f.connect.data)

        # Speed configuration registers.
        m.d.comb += self.low_speed_only.eq(self._control.f.low_speed_only.data)

        m.d.comb += self.full_speed_only.eq(self._control.f.full_speed_only.data)

        # event: bus reset detected
        m.d.comb += self._reset.i.eq(self.bus_reset)

        # connect events to irq line
        m.d.comb += self.irq.eq(self._events.src.i)

        return m
