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



    def elaborate(self, platform: Platform):
        m = Module()
        try:
            spi = platform.request(self.id, self.index)
        except:
            logging.warning(f"Platform does not support {self.id} {self.index}")
            return m
        m.d.comb += [
            spi.copi.oe.eq(self.pins.dq.oe),
            spi.copi.o.eq(self.pins.dq.o),
            self.pins.dq.i.eq(spi.copi.i),
            spi.cs.o.eq(self.pins.cs.o),
            spi.clk.o.eq(self.pins.sck)
        ]
        return m