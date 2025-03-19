#
# This file is part of LUNA.
#
# Copyright (c) 2020-2025 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

""" Implementation of a Triple-FIFO endpoint manager.

Equivalent (but not binary-compatbile) implementation of ValentyUSB's ``eptri``.

For an example, see ``examples/usb/eptri`` or TinyUSB's ``luna/dcd_eptri.c``.
"""

from typing                           import Annotated

from amaranth                         import *
from amaranth.hdl.xfrm                import ResetInserter, DomainRenamer
from amaranth.lib                     import wiring
from amaranth.lib.fifo                import SyncFIFOBuffered
from amaranth.lib.wiring              import In, Out, connect, flipped

from amaranth_soc                     import csr, event

from luna.gateware.usb.usb2.endpoint  import EndpointInterface


class Peripheral(wiring.Component):
    """ Setup component of our `eptri`-equivalent interface.

    Implements the USB Setup FIFO, which handles SETUP packets on any endpoint.

    This interface is similar to an :class:`OutFIFOInterface`, but always ACKs packets,
    and does not allow for any flow control; as a USB device must always be ready to accept
    control packets. [USB2.0: 8.6.1]

    Attributes
    ----------

    interface: EndpointInterface
        Our primary interface to the core USB device hardware.
    """

    class Control(csr.Register, access="w"):
        """ Control register

            address: Controls the current device's USB address. Should be written after a SET_ADDRESS
                     request is received. Automatically resets back to zero on a USB reset.
        """
        address : csr.Field(csr.action.W,       unsigned(8))

    class Status(csr.Register, access="r"):
        """ Status register

            address: Holds the current device's active USB address.
            epno:    The endpoint number associated with the most recently captured SETUP packet.
            have:    `1` iff data is available in the FIFO.
        """
        address : csr.Field(csr.action.R,       unsigned(8))
        epno    : csr.Field(csr.action.R,       unsigned(4))
        have    : csr.Field(csr.action.R,       unsigned(1))
        _0      : csr.Field(csr.action.ResRAW0, unsigned(3))

    class Reset(csr.Register, access="w"):
        """ Reset register

            fifo: Local reset control for the SETUP handler; writing a '1' to this register clears
                  the handler state.
        """
        fifo    : csr.Field(csr.action.W,       unsigned(1))
        _0      : csr.Field(csr.action.ResRAW0, unsigned(7))

    class Data(csr.Register, access="r"):
        """ Data register

            A FIFO that returns the bytes from the most recently captured SETUP packet.
            Reading a byte from this register advances the FIFO. The first eight bytes read
            from this contain the core SETUP packet.
        """
        byte : csr.Field(csr.action.R, unsigned(8))


    def __init__(self):
        # I/O port  FIXME ambiguity - private or signature ?
        self.interface = EndpointInterface()

        # registers
        regs = csr.Builder(addr_width=4, data_width=8)
        self._control = regs.add("control", self.Control())
        self._status  = regs.add("status",  self.Status())
        self._reset   = regs.add("reset",   self.Reset())
        self._data    = regs.add("data",    self.Data())
        self._bridge = csr.Bridge(regs.as_memory_map())

        # events
        from typing import Annotated
        EventSource = Annotated[event.Source, "Interrupt that triggers when a new SETUP packet is ready to be read."]
        self._setup_received = EventSource(path=("setup_received",))
        event_map = event.EventMap()
        event_map.add(self._setup_received)
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

        # Shortcuts to our components.
        interface      = self.interface
        token          = self.interface.tokenizer
        rx             = self.interface.rx
        handshakes_out = self.interface.handshakes_out

        # Logic condition for getting a new setup packet.
        new_setup       = token.new_token & token.is_setup
        reset_requested = self._reset.f.fifo.w_stb & self._reset.f.fifo.w_data
        clear_fifo      = new_setup | reset_requested

        #
        # Core FIFO.
        #
        m.submodules.fifo = fifo = ResetInserter(clear_fifo)(SyncFIFOBuffered(width=8, depth=8))

        m.d.comb += [

            # We'll write to the active FIFO whenever the last received token is a SETUP
            # token, and we have incoming data; and we'll always write the data received
            fifo.w_en                   .eq(token.is_setup & rx.valid & rx.next),
            fifo.w_data                 .eq(rx.payload),

            # We'll advance the FIFO whenever our CPU reads from the data CSR;
            # and we'll always read our data from the FIFO.
            fifo.r_en                   .eq(self._data.f.byte.r_stb),
            self._data.f.byte.r_data    .eq(fifo.r_data),

            # Pass the FIFO status on to our CPU.
            self._status.f.have.r_data  .eq(fifo.r_rdy),

            # Always acknowledge SETUP packets as they arrive.
            handshakes_out.ack          .eq(token.is_setup & interface.rx_ready_for_response),

            # Trigger a SETUP event as we ACK the setup packet, since that's also the point
            # where we know we're done receiving data.
            self._setup_received.i      .eq(handshakes_out.ack)
        ]

        # control registers
        with m.If(self._control.f.address.w_stb):
            m.d.comb += [
                interface.address_changed  .eq(1),
                interface.new_address      .eq(self._control.f.address.w_data),
            ]

        # status registers
        m.d.comb += self._status.f.address.r_data.eq(interface.active_address)
        with m.If(token.new_token & token.is_setup):
            m.d.usb += self._status.f.epno.r_data.eq(token.endpoint)

        # connect events to irq line
        m.d.comb += self.irq.eq(self._events.src.i)

        return DomainRenamer({"sync": "usb"})(m)
