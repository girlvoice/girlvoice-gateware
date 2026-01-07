# This file is based on the luna-soc SPI controller.
#
# Copyright (c) 2024 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

# Based on code from LiteSPI

from amaranth             import Module, DomainRenamer, Signal, unsigned
from amaranth.lib         import wiring
from amaranth.lib.fifo    import AsyncFIFO
from amaranth.lib.cdc       import FFSynchronizer
from amaranth.lib.data    import StructLayout, View
from amaranth.lib.wiring  import In, Out, flipped, connect

from amaranth_soc         import csr
from amaranth_soc         import wishbone
from amaranth_soc.memory import MemoryMap

from luna_soc.gateware.core.spiflash.port                import SPIControlPort


class SPIController(wiring.Component):
    """Wishbone write-only SPI Flash Controller interface.

    Provides a write-only SPI Controller that can be interfaced using CSRs.
    Supports multiple access modes with the help of ``width`` and ``mask`` registers which
    can be used to configure the PHY into any supported SDR mode (single/dual/quad/octal).

    Since this is only being used for write transactions on a fixed width bus, the PHY could probably be simplified
    """

    class Phy(csr.Register, access="rw"):
        """PHY control register

            length : SPI transfer length in bits.
            width  : SPI transfer bus width (1/2/4/8).
            mask   : SPI DQ output enable mask.
        """
        def __init__(self, source):
            super().__init__({
                "length" : csr.Field(csr.action.RW, unsigned(len(source.len))),
                "width"  : csr.Field(csr.action.RW, unsigned(len(source.width))),
                "mask"   : csr.Field(csr.action.RW, unsigned(len(source.mask))),
            })

    class Cs(csr.Register, access="w"):
        """SPI chip select register

            select : SPI chip select signal.
        """
        select : csr.Field(csr.action.W, unsigned(1))

    class Status(csr.Register, access="r"):
        """Status register

             tx_ready : TX FIFO ready to receive data.
        """
        # rx_ready : csr.Field(csr.action.R, unsigned(1))
        tx_ready : csr.Field(csr.action.R, unsigned(1))
        bus_busy : csr.Field(csr.action.R, unsigned(1))

    class Data(csr.Register, access="rw"):
        """Data register

            tx : Write the given byte to the TX FIFO
        """
        def __init__(self, width):
            super().__init__({
                "tx" : csr.Field(csr.action.W, unsigned(width))
            })


    def __init__(self, *, data_width=32, granularity=8, tx_depth=16, name=None, domain="sync", phy_domain="fast"):
        wiring.Component.__init__(self, SPIControlPort(data_width))

        self._domain     = domain
        self._phy_domain = phy_domain

        # layout description for writing to the tx fifo
        self.tx_fifo_layout = StructLayout({
            "data":  len(self.source.data),
            "len":   len(self.source.len),
            "width": len(self.source.width),
            "mask":  len(self.source.mask),
        })

        # fifos
        self._tx_fifo = AsyncFIFO(
            width=len(self.source.payload),
            depth=tx_depth,
            w_domain=self._domain,
            r_domain=self._phy_domain,
        )


        # registers
        regs = csr.Builder(addr_width=5, data_width=8)
        self._phy    = regs.add("phy",    self.Phy(self.source))
        self._cs     = regs.add("cs",     self.Cs())
        self._status = regs.add("status", self.Status())
        self._data   = regs.add("data",   self.Data(data_width))

        # bridge
        self._bridge = csr.Bridge(regs.as_memory_map())

        wb = wishbone.Signature(
            addr_width=2,
            data_width=data_width,
            granularity=granularity
        )

        super().__init__({
            "bus" : In(self._bridge.bus.signature),
            "wb_bus": In(wb)
        })
        self.bus.memory_map = self._bridge.bus.memory_map
        self.wb_bus.memory_map = MemoryMap(
            addr_width=4,
            data_width=8
        )
        self.wb_bus.memory_map.add_resource(self, name=("tx_fifo",), size=4)


    def elaborate(self, platform):
        m = Module()
        m.submodules.bridge = self._bridge

        connect(m, self.bus, self._bridge.bus)

        # FIFOs.
        m.submodules.tx_fifo = tx_fifo = self._tx_fifo

        # Chip select generation.
        cs = Signal()
        m.d.comb += self._status.f.bus_busy.r_data.eq(cs)
        with m.FSM():
            with m.State("RISE"):
                # Enable chip select when the CSR is set to 1 and the TX FIFO contains something.
                m.d.comb += cs.eq(tx_fifo.r_rdy)
                with m.If(cs == 1):
                    m.next = "FALL"
            with m.State("FALL"):
                # Only disable chip select after the current TX FIFO is emptied.
                m.d.comb += cs.eq(self._cs.f.select.w_data | tx_fifo.r_rdy)
                with m.If(cs == 0):
                    m.next = "RISE"

        # Connect FIFOs to PHY streams.
        tx_fifo_payload = View(self.tx_fifo_layout, tx_fifo.w_data)
        m.d.comb += [
            # CSRs to TX FIFO.
            # tx_fifo.w_en                   .eq(self._data.f.tx.w_stb),
            # tx_fifo_payload.data           .eq(self._data.f.tx.w_data),
            tx_fifo_payload.len            .eq(self._phy.f.length.data),
            tx_fifo_payload.width          .eq(1),
            tx_fifo_payload.mask           .eq(1),

            # TX FIFO to SPI PHY (PICO).
            self.source.payload            .eq(tx_fifo.r_data),
            self.source.valid              .eq(tx_fifo.r_rdy),
            tx_fifo.r_en                   .eq(self.source.ready),

            # SPI PHY (POCI) to RX FIFO.
            self.sink.ready                .eq(1),

            # FIFOs ready flags.
            self._status.f.tx_ready.r_data .eq(tx_fifo.w_rdy),
        ]

        m.submodules.cs_cdc = self._cs_cdc = FFSynchronizer(
            cs,
            self.cs,
            o_domain=self._phy_domain,
        )

        wb_bus: wishbone.Interface = self.wb_bus

        # m.d.comb += [
        #     tx_fifo_payload.data.eq(wb_bus.dat_w),
        # ]
        with m.FSM():
            with m.State("IDLE"):
                with m.If(wb_bus.cyc & wb_bus.stb & wb_bus.we & tx_fifo.w_rdy):
                    m.d.sync += tx_fifo.w_en.eq(1)
                    m.d.sync += tx_fifo_payload.data.eq(wb_bus.dat_w)
                    m.d.comb += wb_bus.ack.eq(1)
                    m.next = "ACK"
            with m.State("ACK"):
                m.d.sync += tx_fifo.w_en.eq(0)
                m.d.comb += wb_bus.ack.eq(1)
                m.next = "IDLE"

        # Convert our sync domain to the domain requested by the user, if necessary.
        if self._domain != "sync":
            m = DomainRenamer({"sync": self._domain})(m)

        return m

