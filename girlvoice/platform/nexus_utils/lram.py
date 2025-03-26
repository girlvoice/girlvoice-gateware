from lzma import is_check_supported
from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from amaranth.utils import exact_log2

from amaranth_soc import wishbone
from amaranth_soc.memory import MemoryMap

kB = 1024

class NXLRAM(wiring.Component):
    def __init__(self, init=[]):
        super().__init__({
            "DI": In(32),
            "AD": In(14),
            "BYTEEN_N": In(4),
            "CE": In(1),
            "WE": In(1),
            "CS": In(1),
            "DO":Out(32)
        })

    @property
    def size(self):
        return 512 * kB // 32

    def elaborate(self, platform):
        m = Module()
        m.submodules.lram = Instance("SP512K",
            p_ECC_BYTE_SEL = "BYTE_EN",
            i_DI = self.DI,
            i_AD = self.AD,
            i_BYTEEN_N = self.BYTEEN_N,
            i_CE = self.CE,
            i_WE = self.WE,
            i_CS = self.CS,
            i_CLK = ClockSignal(),
            o_DO = self.DO
        )

        return m

class WishboneNXLRAM(wiring.Component):
    def __init__(self, size, data_width, writable=True, init=[]):
        assert data_width in [32, 64]
        granularity = 8
        self.data_width = data_width
        self.size = size


        if data_width == 32:
            assert size in [64*kB, 128*kB, 192*kB, 256*kB, 320*kB]
            self.depth_cascading = size//(64*kB)
            self.width_cascading = 1
        if data_width == 64:
            assert size in [128*kB, 256*kB]
            self.depth_cascading = size//(128*kB)
            self.width_cascading = 2

        self.addr_width = 14 + self.depth_cascading.bit_length()
        depth = (size * granularity) // data_width
        super().__init__({
            "wb_bus": In(wishbone.Signature(
                            addr_width=exact_log2(depth),
                            data_width=data_width,
                            granularity=granularity
                      ))
        })
        self.wb_bus.memory_map = MemoryMap(addr_width=exact_log2(size), data_width=granularity)

        self._lram_blocks = []
        for d in range(self.depth_cascading):
            self._lram_blocks.append([])
            for w in range(self.width_cascading):
                lram_block = NXLRAM()
                self._lram_blocks[d].append(lram_block)

                self.wb_bus.memory_map.add_resource(lram_block, name=(f"lram{d}{w}",), size=lram_block.size)
        self.wb_bus.memory_map.freeze()


    def elaborate(self, platform):
        m = Module()
        for d in range(self.depth_cascading):

            # Combine RAMs to increase Width.
            for w in range(self.width_cascading):
                lram    = self._lram_blocks[d][w]
                m.d.comb += [
                    lram.DI.eq(self.wb_bus.dat_w[32*w:32*(w+1)]),
                    lram.AD.eq(self.wb_bus.adr[:14]),
                    lram.CE.eq(1),
                    lram.BYTEEN_N.eq(~Mux(self.wb_bus.we, self.wb_bus.sel[4*w:4*(w+1)], 0))
                ]

                with m.If(self.wb_bus.adr[14:14+self.depth_cascading.bit_length()] == d):
                    m.d.comb += [
                        lram.CS.eq(1),
                        lram.WE.eq(self.wb_bus.we & self.wb_bus.stb & self.wb_bus.cyc),
                        self.wb_bus.dat_r[32*w:32*(w+1)].eq(lram.DO)
                    ]

                m.submodules += lram

        m.d.sync += self.wb_bus.ack.eq(self.wb_bus.stb & self.wb_bus.cyc & ~self.wb_bus.ack)

        return m

