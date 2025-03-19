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
    """ OUT component of our `eptri`

    Implements the OUT FIFO, which handles receiving packets from our host.

    Attributes
    ----------

    interface: EndpointInterface
        Our primary interface to the core USB device hardware.
    """

    class Control(csr.Register, access="rw"):
        """ Control register

            address: Controls the current device's USB address. Should be written after a SET_ADDRESS request
                     is received. Automatically resets back to zero on a USB reset.
        """
        address : csr.Field(csr.action.RW,      unsigned(8))

    class Endpoint(csr.Register, access="rw"):
        """ Endpoint register

            number: Selects the endpoint number to prime. This interface allows priming multiple endpoints
            at once. That is, multiple endpoints can be ready to receive data at a time. See the `prime`
            and `enable` bits for usage.
        """
        number : csr.Field(csr.action.RW,      unsigned(4))
        _0     : csr.Field(csr.action.ResRAW0, unsigned(4))

    class Enable(csr.Register, access="w"):
        """ Enable register

            enabled: Controls whether any data can be received on any primed OUT endpoint. This bit is
                     automatically cleared on receive in order to give the controller time to read data
                     from the FIFO. It must be re-enabled once the FIFO has been emptied.
        """
        enabled : csr.Field(csr.action.W,       unsigned(1))
        _0      : csr.Field(csr.action.ResRAW0, unsigned(7))

    class Prime(csr.Register, access="w"):
        """ Prime register

            primed: Controls "priming" an out endpoint. To receive data on any endpoint, the CPU must first
                    select the endpoint with the `epno` register; and then write a '1' into the prime and
                    enable register. This prepares our FIFO to receive data; and the next OUT transaction will
                    be captured into the FIFO.

                    When a transaction is complete, the `enable` bit is reset; the `prime` is not. This
                    effectively means that `enable` controls receiving on _any_ of the primed endpoints;
                    while `prime` can be used to build a collection of endpoints willing to participate in
                    receipt.

                    Note that this does not apply to the control endpoint. Once the control endpoint has
                    received a packet it will be un-primed and need to be re-primed before it can receive
                    again. This is to ensure that we can establish an order on the receipt of the setup
                    packet and any associated data.

                    Only one transaction / data packet is captured per `enable` write; repeated enabling is
                    necessary to capture multiple packets.
        """
        primed : csr.Field(csr.action.W,       unsigned(1))
        _0     : csr.Field(csr.action.ResRAW0, unsigned(7))

    class Stall(csr.Register, access="w"):
        """ Stall register

            stalled: Controls STALL'ing the active endpoint. Setting or clearing this bit will set or clear
                     STALL on the provided endpoint. Endpoint STALLs persist even after `epno` is changed; so
                     multiple endpoints can be stalled at once by writing their respective endpoint numbers
                     into `epno` register and then setting their `stall` bits.
        """
        stalled : csr.Field(csr.action.W,       unsigned(1))
        _0      : csr.Field(csr.action.ResRAW0, unsigned(7))

    class Pid(csr.Register, access="w"):
        """ Pid register

            toggle: Sets the current PID toggle bit for the given endpoint.
        """
        toggle : csr.Field(csr.action.W,       unsigned(1))
        _0     : csr.Field(csr.action.ResRAW0, unsigned(7))

    class Status(csr.Register, access="r"):
        """ Status register

            epno: Contains the endpoint number associated with the data in the FIFO -- that is,
                  the endpoint number on which the relevant data was received.
            have: `1` iff data is available in the FIFO.
            pid:  Contains the current PID toggle bit for the given endpoint.
        """
        epno : csr.Field(csr.action.R,  unsigned(4))
        _0   : csr.Field(csr.action.ResRAW0, unsigned(4))
        have : csr.Field(csr.action.R,       unsigned(1))
        pid  : csr.Field(csr.action.R,       unsigned(1))
        _1   : csr.Field(csr.action.ResRAW0, unsigned(6))

    class Reset(csr.Register, access="w"):
        """ Reset register

            fifo: Local reset for the OUT handler; clears the out FIFO.
        """
        fifo : csr.Field(csr.action.W,       unsigned(1))
        _0   : csr.Field(csr.action.ResRAW0, unsigned(7))

    class Data(csr.Register, access="r"):
        """ Data register

            Read-only register. A FIFO that returns the bytes from the most recently captured OUT transaction.
            Reading a byte from this register advances the FIFO.

            byte:    Contains the most recently received byte.
        """
        byte : csr.Field(csr.action.R,       unsigned(8))


    def __init__(self, max_packet_size=512):
        """
        Parameters
        ----------
            max_packet_size: int, optional
                Sets the maximum packet size that can be transmitted on this endpoint.
                This should match the value provided in the relevant endpoint descriptor.
        """

        self._max_packet_size = max_packet_size

        # I/O port   FIXME ambiguity - private, or use a signature?
        self.interface = EndpointInterface()

        # registers
        regs = csr.Builder(addr_width=5, data_width=8)
        self._control  = regs.add("control",  self.Control())
        self._endpoint = regs.add("endpoint", self.Endpoint())
        self._enable   = regs.add("enable",   self.Enable())
        self._prime    = regs.add("prime",    self.Prime())
        self._stall    = regs.add("stall",    self.Stall())
        self._pid      = regs.add("pid",      self.Pid())
        self._status   = regs.add("status",   self.Status())
        self._reset    = regs.add("reset",    self.Reset())
        self._data     = regs.add("data",     self.Data())
        self._bridge   = csr.Bridge(regs.as_memory_map())

        # events
        EventSource = Annotated[event.Source, "Indicates that an ``OUT`` packet has successfully been transferred from the host. This bit must be cleared in order to receive additional packets."]
        self._done = EventSource(path=("done",))
        event_map = event.EventMap()
        event_map.add(self._done)
        self._events = csr.event.EventMonitor(event_map, data_width=8)

        # csr decoder
        self._decoder = csr.Decoder(addr_width=6, data_width=8)
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

        #
        # Control registers
        #

        # Keep track of which endpoints are primed.
        endpoint_primed   = Array(Signal() for _ in range(16))

        # Keep track of which endpoints are stalled.
        endpoint_stalled  = Array(Signal() for _ in range(16))

        # Keep track of the PIDs for each endpoint, which we'll toggle automatically.
        endpoint_data_pid = Array(Signal() for _ in range(16))

        # Keep track of whether our FIFO is ready to receive a new packet.
        fifo_ready = Signal()

        # Keep track of whether we're enabled.
        enabled = Signal()
        with m.If(self._enable.f.enabled.w_stb):
            m.d.usb += enabled.eq(self._enable.f.enabled.w_data)

        # If Prime is written to, mark the relevant endpoint as primed.
        with m.If(self._prime.f.primed.w_stb):
            m.d.usb += endpoint_primed[self._endpoint.f.number.data].eq(self._prime.f.primed.w_data)

        # If we've just ACK'd a receive, clear our enable and
        # clear our FIFO's ready state.
        with m.If(interface.handshakes_out.ack & token.is_out):
            m.d.usb += [
                enabled                          .eq(0),
                fifo_ready                       .eq(0),
            ]
            # If we've ACK'd a receive on the control endpoint, un-prime it to
            # ensure we only receive control data _after_ we've had an opportunity
            # to receive the setup packet.
            with m.If(token.endpoint == 0):
                m.d.usb += endpoint_primed[token.endpoint].eq(0)

        # Mark our FIFO as ready iff it is enabled and primed on receipt of a new token.
        with m.If(token.new_token & enabled & endpoint_primed[token.endpoint]):
            m.d.usb += fifo_ready.eq(1)

        # Set the value of our endpoint `stall` based on our `stall` register...
        with m.If(self._stall.f.stalled.w_stb):
            m.d.usb += endpoint_stalled[self._endpoint.f.number.data].eq(self._stall.f.stalled.w_data)

        # Allow our controller to override our DATA pid, selectively.
        with m.If(self._pid.f.toggle.w_stb):
            m.d.usb += endpoint_data_pid[self._endpoint.f.number.data].eq(self._pid.f.toggle.w_data)

        # Clear our endpoint `stall` when we get a SETUP packet, and reset the endpoint's
        # data PID to DATA1, as per [USB2.0: 8.5.3], the first packet of the DATA or STATUS
        # phase always carries a DATA1 PID.
        with m.If(token.is_setup & token.new_token):
            m.d.usb += [
                endpoint_stalled[token.endpoint]   .eq(0),
                endpoint_data_pid[token.endpoint]  .eq(1)
            ]

        #
        # Core FIFO.
        #
        m.submodules.fifo = fifo = ResetInserter(self._reset.f.fifo.w_stb)(
            SyncFIFOBuffered(width=8, depth=self._max_packet_size)
        )

        # Shortcut for when we should allow a receive. We'll read when:
        #  - Our `epno` register matches the target register; and
        #  - We've primed the relevant endpoint.
        #  - Our most recent token is an OUT.
        #  - We're not stalled.
        stalled            = token.is_out & endpoint_stalled[token.endpoint]
        is_endpoint_primed = endpoint_primed[token.endpoint]
        ready_to_receive   = fifo_ready & is_endpoint_primed & enabled & ~stalled
        allow_receive      = token.is_out & ready_to_receive
        nak_receives       = token.is_out & ~ready_to_receive & ~stalled

        # Shortcut for when we have a "redundant"/incorrect PID. In these cases, we'll assume
        # the host missed our ACK, and per the USB spec, implicitly ACK the packet.
        is_redundant_pid    = (interface.rx_pid_toggle != endpoint_data_pid[token.endpoint])
        is_redundant_packet = is_endpoint_primed & token.is_out & is_redundant_pid

        # Shortcut conditions under which we'll ACK and NAK a receive.
        ack_redundant_packet = (is_redundant_packet & interface.rx_ready_for_response)
        ack_receive          = allow_receive & interface.rx_ready_for_response
        nak_receive          = nak_receives  & interface.rx_ready_for_response & ~ack_redundant_packet

        # Conditions under which we'll ACK or NAK a ping.
        ack_ping         = ready_to_receive  & token.is_ping & token.ready_for_response
        nak_ping         = ~ready_to_receive & token.is_ping & token.ready_for_response

        m.d.comb += [
            # We'll write to the endpoint iff we've valid data, and we're allowed receive.
            fifo.w_en                   .eq(allow_receive & rx.valid & rx.next & ~is_redundant_packet),
            fifo.w_data                 .eq(rx.payload),

            # We'll advance the FIFO whenever our CPU reads from the data CSR;
            # and we'll always read our data from the FIFO.
            fifo.r_en                   .eq(self._data.f.byte.r_stb),
            self._data.f.byte.r_data    .eq(fifo.r_data),

            # Pass the FIFO status on to our CPU.
            self._status.f.have.r_data  .eq(fifo.r_rdy),

            # If we've just finished an allowed receive, ACK.
            handshakes_out.ack          .eq(ack_receive | ack_ping | ack_redundant_packet),

            # Trigger our DONE interrupt once we ACK a received/allowed packet.
            self._done.i                .eq(ack_receive),

            # If we were stalled, stall.
            handshakes_out.stall        .eq(stalled & interface.rx_ready_for_response),

            # If we're not ACK'ing or STALL'ing, NAK all packets.
            handshakes_out.nak          .eq(nak_receive | nak_ping),

            # Always indicate the current DATA PID in the PID register.
            self._status.f.pid.r_data   .eq(endpoint_data_pid[self._endpoint.f.number.data])
        ]

        # Whenever we capture data, update our associated endpoint number
        # to match the endpoint on which we received the relevant data.
        with m.If(token.new_token & token.is_out):
            m.d.usb += self._status.f.epno.r_data.eq(token.endpoint)

        # Whenever we ACK a non-redundant receive, toggle our DATA PID.
        # (unless the user happens to be overriding it by writing to the PID register).
        with m.If(ack_receive & ~is_redundant_packet & ~self._pid.f.toggle.w_stb):
            m.d.usb += endpoint_data_pid[token.endpoint].eq(~endpoint_data_pid[token.endpoint])

        # connect events to irq line
        m.d.comb += self.irq.eq(self._events.src.i)

        return DomainRenamer({"sync": "usb"})(m)
