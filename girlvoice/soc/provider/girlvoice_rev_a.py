import logging

from amaranth             import *
from amaranth.build       import Platform
from amaranth.lib         import wiring
from amaranth.lib.wiring  import Component, In, Out

from luna_soc.gateware.core import spiflash

class SPIFlashProvider(Component):
    def __init__(self, id="spi_flash", index=0):
        self.id    = id
        self.index = index
        super().__init__({
            "pins": In(spiflash.PinSignature())
        })

        self.pins.sck = Signal()

    def elaborate(self, platform: Platform):
        m = Module()
        try:
            spi = platform.request(self.id, self.index)
        except:
            logging.warning(f"Platform does not support {self.id} {self.index}")
            return m

        # This is the LCD display SPI interface
        if self.id == "spi":
            m.d.comb += [
                spi.copi.oe.eq(self.pins.dq.oe),
                spi.copi.o.eq(self.pins.dq.o),
                self.pins.dq.i.eq(spi.copi.i),
                spi.cs.o.eq(self.pins.cs.o),
                spi.clk.o.eq(self.pins.sck)
            ]
        if self.id == "spi_flash_4x":
            m.d.comb += [
                self.pins.dq.i.eq(spi.dq.i),
                spi.dq.o.eq(self.pins.dq.o),
                spi.dq.oe.eq(self.pins.dq.oe),
                spi.cs.o.eq(self.pins.cs.o)
            ]
        return m

