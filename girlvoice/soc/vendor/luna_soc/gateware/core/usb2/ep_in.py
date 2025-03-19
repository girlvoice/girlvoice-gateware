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
    """ IN component of our `eptri`-equivalent interface.

    Implements the FIFO that handles `eptri` IN requests. This FIFO collects USB data, and
    transmits it in response to an IN token. Like all `eptri` interfaces; it can handle only one
    pending packet at a time.


    Attributes
    ----------

    interface: EndpointInterface
        Our primary interface to the core USB device hardware.

    """

    class Endpoint(csr.Register, access="w"):
        """ Endpoint register

            number: Contains the endpoint the enqueued packet is to be transmitted on. Writing to this field
                    marks the relevant packet as ready to transmit; and thus should only be written after a
                    full packet has been written into the FIFO. If no data has been placed into the DATA FIFO,
                    a zero-length packet is generated.
                    Note that any IN requests that do not match the endpoint number are automatically NAK'd.
        """
        number : csr.Field(csr.action.W,       unsigned(4))
        _0     : csr.Field(csr.action.ResRAW0, unsigned(4))

    class Stall(csr.Register, access="w"):
        """ Stall register

            stalled: When this field contains '1', any IN tokens targeting `epno` will be responded to with a
                     STALL token, rather than DATA or a NAK.
                     For EP0, this field will automatically be cleared when a new SETUP token is received.
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

            nak:  Contains a bitmask of endpoints that have responded with a NAK since the
                  last read of this register.
            epno: Contains the endpoint being transmitted on.
            idle: This value is `1` if no packet is actively being transmitted.
            have: This value is `1` if data is present in the transmit FIFO.
            pid:  Contains the current PID toggle bit for the given endpoint.
        """
        nak  : csr.Field(csr.action.R,        unsigned(16))
        epno : csr.Field(csr.action.R,        unsigned(4))
        _0   : csr.Field(csr.action.ResRAW0,  unsigned(4))
        idle : csr.Field(csr.action.R,        unsigned(1))
        have : csr.Field(csr.action.R,        unsigned(1))
        pid  : csr.Field(csr.action.R,        unsigned(1))
        _1   : csr.Field(csr.action.ResRAW0,  unsigned(5))

    class Reset(csr.Register, access="w"):
        """ Reset register

            fifo: A write to this field Clears the FIFO without transmitting.
        """
        fifo : csr.Field(csr.action.W,       unsigned(1))
        _1   : csr.Field(csr.action.ResRAW0, unsigned(7))

    class Data(csr.Register, access="w"):
        """ Data register

            Each write enqueues a byte to be transmitted; gradually building a single packet to
            be transmitted. This queue should only ever contain a single packet; it is the software's
            responsibility to handle breaking requests down into packets.
        """
        byte : csr.Field(csr.action.W, unsigned(8)) # desc="" ?


    def __init__(self, max_packet_size=512):
        """
        Parameters
        ----------
            max_packet_size: int, optional
                Sets the maximum packet size that can be transmitted on this endpoint.
                This should match the value provided in the relevant endpoint descriptor.
        """

        self._max_packet_size = max_packet_size

        # I/O port   FIXME ambiguity - private or signature ?
        self.interface = EndpointInterface()

        # registers
        regs = csr.Builder(addr_width=4, data_width=8)
        self._endpoint = regs.add("endpoint", self.Endpoint())
        self._stall    = regs.add("stall",    self.Stall())
        self._pid      = regs.add("pid",      self.Pid())
        self._status   = regs.add("status",   self.Status())
        self._reset    = regs.add("reset",    self.Reset())
        self._data     = regs.add("data",     self.Data())
        self._bridge   = csr.Bridge(regs.as_memory_map())

        # events
        EventSource = Annotated[event.Source, "Indicates that the host has successfully transferred an ``IN`` packet, and that the FIFO is now empty."]
        self._done = EventSource(path=("done",))
        event_map = event.EventMap()
        event_map.add(self._done)
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
        token          = self.interface.tokenizer
        tx             = self.interface.tx
        handshakes_out = self.interface.handshakes_out

        #
        # Core FIFO.
        #

        # Create our FIFO; and set it to be cleared whenever the user requests.
        m.submodules.fifo = fifo = ResetInserter(self._reset.f.fifo.w_stb)(
            SyncFIFOBuffered(width=8, depth=self._max_packet_size)
        )

        m.d.comb += [
            # Whenever the user DATA register is written to, add the relevant data to our FIFO.
            fifo.w_en         .eq(self._data.f.byte.w_stb),
            fifo.w_data       .eq(self._data.f.byte.w_data),
        ]

        # Keep track of the amount of data in our FIFO.
        bytes_in_fifo = Signal(range(0, self._max_packet_size + 1))

        # If we're clearing the whole FIFO, reset our data count.
        with m.If(self._reset.f.fifo.w_stb):
            m.d.usb += bytes_in_fifo.eq(0)

        # Keep track of our FIFO's data count as data is added or removed.
        increment = fifo.w_en & fifo.w_rdy
        decrement = fifo.r_en & fifo.r_rdy

        with m.Elif(increment & ~decrement):
            m.d.usb += bytes_in_fifo.eq(bytes_in_fifo + 1)
        with m.Elif(decrement & ~increment):
            m.d.usb += bytes_in_fifo.eq(bytes_in_fifo - 1)


        #
        # Register updates.
        #

        # Active endpoint number.
        with m.If(self._endpoint.f.number.w_stb):
            m.d.usb += self._status.f.epno.r_data.eq(self._endpoint.f.number.w_data)

        # Keep track of which endpoints are stalled.
        endpoint_stalled  = Array(Signal() for _ in range(16))

        # Keep track of the current DATA pid for each endpoint.
        endpoint_data_pid = Array(Signal() for _ in range(16))

        # Keep track of which endpoints have responded with a NAK.
        endpoint_nakked  = Array(Signal() for _ in range(16))

        # Clear our system state on reset.
        with m.If(self._reset.f.fifo.w_stb):
            for i in range(16):
                m.d.usb += [
                    endpoint_stalled[i]   .eq(0),
                    endpoint_data_pid[i]  .eq(0),
                    endpoint_nakked[i]    .eq(0),
                ]

        # Set the value of our endpoint `stall` based on our `stall` register...
        with m.If(self._stall.f.stalled.w_stb):
            m.d.usb += endpoint_stalled[self._status.f.epno.r_data].eq(self._stall.f.stalled.w_data)

        # Clear our endpoint `stall` when we get a SETUP packet, and reset the endpoint's
        # data PID to DATA1, as per [USB2.0: 8.5.3], the first packet of the DATA or STATUS
        # phase always carries a DATA1 PID.
        with m.If(token.is_setup & token.new_token):
            m.d.usb += [
                endpoint_stalled[token.endpoint]   .eq(0),
                endpoint_data_pid[token.endpoint]  .eq(1),
            ]


        #
        # Status registers.
        #

        m.d.comb += [
            self._status.f.have.r_data .eq(fifo.r_rdy),
            self._status.f.pid.r_data  .eq(endpoint_data_pid[self._status.f.epno.r_data]),
            self._status.f.nak.r_data  .eq(Cat(endpoint_nakked)),
        ]


        #
        # Data toggle control.
        #

        endpoint_matches = (token.endpoint == self._status.f.epno.r_data)
        packet_complete  = self.interface.handshakes_in.ack & token.is_in & endpoint_matches

        # Always drive the DATA pid we're transmitting with our current data pid.
        m.d.comb += self.interface.tx_pid_toggle.eq(endpoint_data_pid[token.endpoint])

        # If our controller is overriding the data PID, accept the override.
        with m.If(self._pid.f.toggle.w_stb):
            m.d.usb += endpoint_data_pid[self._status.f.epno.r_data].eq(self._pid.f.toggle.w_data)

        # Otherwise, toggle our expected DATA PID once we receive a complete packet.
        with m.Elif(packet_complete):
            m.d.usb += endpoint_data_pid[token.endpoint].eq(~endpoint_data_pid[token.endpoint])


        #
        # Control logic.
        #

        # Logic shorthand.
        new_in_token     = (token.is_in & token.ready_for_response)
        stalled          = endpoint_stalled[token.endpoint]

        with m.FSM(domain='usb') as f:

            # Drive our IDLE line based on our FSM state.
            m.d.comb += self._status.f.idle.r_data.eq(f.ongoing('IDLE'))

            # IDLE -- our CPU hasn't yet requested that we send data.
            # We'll wait for it to do so, and NAK any packets that arrive.
            with m.State("IDLE"):

                # If we get an IN token...
                with m.If(new_in_token):

                    # STALL it, if the endpoint is STALL'd...
                    with m.If(stalled):
                        m.d.comb += handshakes_out.stall.eq(1)

                    # Otherwise, NAK.
                    with m.Else():
                        m.d.comb += handshakes_out.nak.eq(1)
                        m.d.usb += endpoint_nakked[token.endpoint].eq(1)

                # If the user request that we send data, "prime" the endpoint.
                # This means we have data to send, but are just waiting for an IN token.
                with m.If(self._endpoint.f.number.w_stb & ~stalled):
                    # we can also clear our NAK status now
                    m.d.usb += endpoint_nakked[token.endpoint].eq(0)
                    m.next = "PRIMED"

                # Always return to IDLE on reset.
                with m.If(self._reset.f.fifo.w_stb):
                    m.next = "IDLE"

            # PRIMED -- our CPU has provided data, but we haven't been sent an IN token, yet.
            # Await that IN token.
            with m.State("PRIMED"):

                with m.If(new_in_token):

                    # If the target endpoint is STALL'd, reply with STALL no matter what.
                    with m.If(stalled):
                        m.d.comb += handshakes_out.stall.eq(1)

                    # If we have a new IN token to our endpoint, move to responding to it.
                    with m.Elif(endpoint_matches):

                        # If there's no data in our endpoint, send a ZLP.
                        with m.If(~fifo.r_rdy):
                            m.next = "SEND_ZLP"

                        # Otherwise, send our data, starting with our first byte.
                        with m.Else():
                            m.d.usb += tx.first.eq(1)
                            m.next = "SEND_DATA"

                    # Otherwise, we don't have a response; NAK the packet.
                    with m.Else():
                        m.d.comb += handshakes_out.nak.eq(1)

                # Always return to IDLE on reset.
                with m.If(self._reset.f.fifo.w_stb):
                    m.next = "IDLE"

            # SEND_ZLP -- we're now now ready to respond to an IN token with a ZLP.
            # Send our response.
            with m.State("SEND_ZLP"):
                m.d.comb += [
                    tx.valid  .eq(1),
                    tx.last   .eq(1)
                ]
                # Trigger our DONE event.
                m.d.comb += self._done.i.eq(1)
                m.next = 'IDLE'

            # SEND_DATA -- we're now ready to respond to an IN token to our endpoint.
            # Send our response.
            with m.State("SEND_DATA"):
                last_byte = (bytes_in_fifo == 1)

                m.d.comb += [
                    tx.valid    .eq(1),
                    tx.last     .eq(last_byte),

                    # Drive our transmit data directly from our FIFO...
                    tx.payload  .eq(fifo.r_data),

                    # ... and advance our FIFO each time a data byte is transmitted.
                    fifo.r_en   .eq(tx.ready)
                ]

                # After we've sent a byte, drop our first flag.
                with m.If(tx.ready):
                    m.d.usb += tx.first.eq(0)

                # Once we transmit our last packet, we're done transmitting. Move back to IDLE.
                with m.If(last_byte & tx.ready):
                    # Trigger our DONE event.
                    m.d.comb += self._done.i.eq(1)
                    m.next = 'IDLE'

                # Always return to IDLE on reset.
                with m.If(self._reset.f.fifo.w_stb):
                    m.next = "IDLE"

        # connect events to irq line
        m.d.comb += self.irq.eq(self._events.src.i)

        return DomainRenamer({"sync": "usb"})(m)
