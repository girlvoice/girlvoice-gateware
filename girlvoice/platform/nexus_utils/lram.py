from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out

from amaranth.utils import exact_log2

from amaranth_soc import wishbone
from amaranth_soc.memory import MemoryMap

kB = 1024

def initval_parameters(contents, width=32):
    """
    In Radiant, initial values for LRAM are passed a sequence of parameters
    named INITVAL_00 ... INITVAL_7F. Each parameter value contains 4096 bits
    of data, encoded as a 1280-digit hexadecimal number, with
    alternating sequences of 8 bits of padding and 32 bits of real data,
    making up 64KiB altogether.

    Adapted from Litex
    """
    assert width in [32]
    # Each LRAM is 64KiB == 524288 bits
    assert len(contents) == 524288 // width, f"{len(contents)} is not formatted for {524288 // width} words"
    chunk_size = 4096 // width
    parameters = {}
    with open("init_params.txt", "a") as f:
        for i in range(0x80):
            offset = chunk_size * i
            if width == 32:
                value = '0x' + ''.join('00{:08X}'.format(contents[offset + j])
                                       for j in range(chunk_size - 1, -1, -1))
            elif width == 64:
                value = '0x' + ''.join('00{:08X}00{:08X}'.format(contents[offset + j] >> 32, contents[offset + j] | 0xFFFFFFFF)
                                       for j in range(chunk_size - 1, -1, -1))
            parameters['p_INITVAL_{:02X}'.format(i)] = value

            f.write('p_INITVAL_{:02X}={}\n'.format(i, value))
    return parameters

class NXLRAM(wiring.Component):
    """
    Wrapper for the CrosslinkNX Large RAM module
    """

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
        self.params = {}

        self.params.update(
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

        if init != []:
            self._init = init

    @property
    def size(self):
        return 512 * kB // 32

    @property
    def init(self):
        return self._init

    @init.setter
    def init(self, init):
        self.params.update(initval_parameters(init))
        self._init = init

    def elaborate(self, platform):
        m = Module()
        m.submodules.lram = Instance("SP512K", **self.params)
        return m

class WishboneNXLRAM(wiring.Component):
    def __init__(self, size, data_width, writable=True, init=[]):
        assert data_width in [32, 64]
        granularity = 8
        self.data_width = data_width
        self.size = size
        self.writable=writable

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
                            granularity=granularity,
                            features={"cti", "bte"}
                      ))
        })
        self.wb_bus.memory_map = MemoryMap(addr_width=exact_log2(size), data_width=granularity)

        self._lram_blocks = []
        print(self.depth_cascading)
        for d in range(self.depth_cascading):
            self._lram_blocks.append([])
            for w in range(self.width_cascading):
                lram_block = NXLRAM()
                self._lram_blocks[d].append(lram_block)

                self.wb_bus.memory_map.add_resource(lram_block, name=(f"lram{d}{w}",), size=lram_block.size)
        self.wb_bus.memory_map.freeze()

        self._init = []
        if len(init) != 0:
            self._set_init(init)


    def _set_init(self, data: list[int]):
        data += [0] * ((self.size * 8) // self.data_width - len(data))
        mem_size_words = 64 * kB * 8 // self.data_width
        for d in range(self.depth_cascading):
            for w in range(self.width_cascading):
                offset = d * self.width_cascading * mem_size_words + w * mem_size_words
                chunk = data[offset:offset + mem_size_words]
                self._lram_blocks[d][w].init = chunk

        self._init = data
    @property
    def init(self):
        return self._init

    @init.setter
    def init(self, init):
        return self._set_init(init)

    def elaborate(self, platform):
        m = Module()

        data_r = Signal(self.data_width)
        data_w = Signal(self.data_width)

        addr = Signal(self.addr_width)
        incr = Signal.like(self.wb_bus.adr)

        m.d.comb += [
            self.wb_bus.dat_r.eq(data_r),
        ]

        with m.Switch(self.wb_bus.bte):
            with m.Case(wishbone.BurstTypeExt.LINEAR):
                m.d.comb += incr.eq(self.wb_bus.adr + 1)
            with m.Case(wishbone.BurstTypeExt.WRAP_4):
                m.d.comb += incr[:2].eq(self.wb_bus.adr[:2] + 1)
                m.d.comb += incr[2:].eq(self.wb_bus.adr[2:])
            with m.Case(wishbone.BurstTypeExt.WRAP_8):
                m.d.comb += incr[:3].eq(self.wb_bus.adr[:3] + 1)
                m.d.comb += incr[3:].eq(self.wb_bus.adr[3:])
            with m.Case(wishbone.BurstTypeExt.WRAP_16):
                m.d.comb += incr[:4].eq(self.wb_bus.adr[:4] + 1)
                m.d.comb += incr[4:].eq(self.wb_bus.adr[4:])

        if self.writable:
            m.d.comb += data_w.eq(self.wb_bus.dat_w)

        with m.If(self.wb_bus.cyc & self.wb_bus.stb):
            m.d.sync += self.wb_bus.ack.eq(1)
            with m.If((self.wb_bus.cti == wishbone.CycleType.INCR_BURST) & self.wb_bus.ack):
                m.d.comb += addr.eq(incr)
            with m.Else():
                m.d.comb += addr.eq(self.wb_bus.adr)

        for d in range(self.depth_cascading):
            # Combine RAMs to increase Width.
            for w in range(self.width_cascading):
                lram    = self._lram_blocks[d][w]
                m.d.comb += [
                    lram.DI.eq(data_w[32*w:32*(w+1)]),
                    lram.AD.eq(addr[:14]),
                    lram.CE.eq(1),
                    lram.BYTEEN_N.eq(~Mux(self.wb_bus.we, self.wb_bus.sel[4*w:4*(w+1)], 0))
                ]

                with m.If(self.wb_bus.adr[14:14+self.depth_cascading.bit_length()] == d):
                    m.d.comb += [
                        lram.CS.eq(1),
                        lram.WE.eq(self.wb_bus.we & self.wb_bus.stb & self.wb_bus.cyc),
                        data_r[32*w:32*(w+1)].eq(lram.DO)
                    ]

                m.submodules += lram

        m.d.sync += self.wb_bus.ack.eq(
            self.wb_bus.stb &
            self.wb_bus.cyc &
            ~self.wb_bus.ack
        )

        return m

