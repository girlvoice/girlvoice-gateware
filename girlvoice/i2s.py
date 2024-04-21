#!/usr/bin/env python3
import os
from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import Out, In

from amaranth.sim import Simulator, Tick

from girlvoice.stream import Stream

class i2s_tx(wiring.Component):
    sink: In(Stream(32))

    lrclk: Out(1)
    sclk: Out(1)
    sdout: Out(1)

    def __init__(self, sys_clk_freq, sclk_freq, sample_width=32):
        self.clk_ratio = int(sys_clk_freq // sclk_freq)
        self.sample_width = sample_width
        super().__init__()

    def elaborate(self, platform):
        m = Module()

        cd_sclk = m.domains.sclk = ClockDomain(local=True, clk_edge="neg")
        m.d.comb += cd_sclk.clk.eq(self.sclk)

        clk_div = Signal(range(self.clk_ratio))
        bit_count = Signal(range(32))
        shift_out = Signal(self.sample_width)

        with m.If(clk_div == (self.clk_ratio - 1) // 2):
            m.d.sync += self.sclk.eq(~self.sclk)
            m.d.sync += clk_div.eq(clk_div + 1)
        with m.Elif(clk_div >= (self.clk_ratio - 1)):
            m.d.sync += clk_div.eq(0)
            m.d.sync += self.sclk.eq(~self.sclk)
            m.d.sync += shift_out.eq (shift_out << 1)
        with m.Else():
            m.d.sync += clk_div.eq(clk_div + 1)

        m.d.sclk += bit_count.eq(bit_count + 1)
        with m.If(bit_count == 31):
            m.d.sclk += self.lrclk.eq(~self.lrclk)
            with m.If(clk_div == (self.clk_ratio - 2)):
                m.d.sync += self.sink.ready.eq(1)

        m.d.sclk += self.sdout.eq(shift_out[self.sample_width - 1])

        with m.If(self.sink.valid & self.sink.ready):
            m.d.sync += shift_out.eq(self.sink.data)
            m.d.sync += self.sink.ready.eq(0)


        return m

class i2s_rx(wiring.Component):
    # To fabric IO
    source: Out(Stream(32))

    # I2S IO
    lrclk: Out(1)
    sclk: Out(1)
    sdin: In(1)

    def __init__(self, sys_clk_freq, sclk_freq, sample_width=18):
        self.clk_ratio = int(sys_clk_freq // sclk_freq)
        self.sample_width = sample_width
        super().__init__()

    def elaborate(self, platform):
        m = Module()

        # cd_sclk = m.domains.sclk = ClockDomain(local=True, clk_edge="neg")
        # m.d.comb += cd_sclk.clk.eq(self.sclk)

        sclk_last = Signal()
        sclk_edge = Signal()

        m.d.sync += sclk_edge.eq(self.sclk ^ sclk_last)
        m.d.sync += sclk_last.eq(self.sclk)

        clk_div = Signal(range(self.clk_ratio))

        shift_reg = Signal(32)
        bit_count = Signal(range(32))

        with m.If(clk_div >= (self.clk_ratio - 1) // 2):
            m.d.sync += clk_div.eq(0)
            m.d.sync += self.sclk.eq(~self.sclk)
        with m.Else():
            m.d.sync += clk_div.eq(clk_div + 1)

        with m.If(sclk_edge):
            m.d.sync += bit_count.eq(bit_count + 1)

        with m.If((bit_count == 31)):
            with m.If(sclk_edge):
                m.d.sync += self.lrclk.eq(~self.lrclk)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(sclk_edge):
                    m.d.sync += shift_reg.eq(0)
                with m.If(bit_count == 0):
                    m.next = "READ"
            with m.State("READ"):
                with m.If(sclk_edge):

                    m.d.sync += shift_reg.eq(shift_reg << 1 | self.sdin)

                with m.If(bit_count >= self.sample_width):

                    m.d.sync += self.source.data.eq(shift_reg)
                    m.d.sync += self.source.valid.eq(1)
                    m.next = "IDLE"

        with m.If(self.source.valid & self.source.ready):
            m.d.sync += self.source.valid.eq(0)

        return m


# class i2s(wiring.Component):
#     source: Out(Stream(32))
#     sink: In(Stream(32))

#     sclk: Out(1)

#     def __init__(self, sys_clk_freq, sclk_freq):
#         self.clk_ratio = int(sys_clk_freq // sclk_freq)
#         super().__init__()

#     def elaborate(self, platform):
#         m = Module()

#         m.submodules.rx = rx = i2s_rx()
#         m.submodules.tx = tx = i2s_tx()

#         cd_sclk = m.domains.sclk = ClockDomain(local=True, clk_edge="neg")
#         m.d.comb += cd_sclk.clk.eq(self.sclk)


#         clk_div = Signal(range(self.clk_ratio))
#         with m.If(clk_div >= (self.clk_ratio - 1) // 2):
#             m.d.sync += clk_div.eq(0)
#             m.d.sync += self.sclk.eq(~self.sclk)
#         with m.Else():
#             m.d.sync += clk_div.eq(clk_div + 1)

#         return m

def tx_tb():
    sys_clk_freq = 40e6
    sclk_freq = 4e6
    dut = i2s_tx(sys_clk_freq=sys_clk_freq, sclk_freq=sclk_freq)
    sim = Simulator(dut)

    samples = [(C(i, 32) ) for i in range(32)]

    def process():
        while (yield ~dut.sink.ready):
                yield Tick()

        for i in range(len(samples)):
            yield dut.sink.data.eq(samples[i])
            yield dut.sink.valid.eq(1)
            yield Tick()
            # yield dut.sink.valid.eq(0)
            while (yield ~dut.sink.ready):
                yield Tick()

    sim.add_process(process)
    sim.add_clock(1 / sys_clk_freq)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()

def rx_tb():
    sys_clk_freq = 24e6
    sclk_freq = 4e6
    dut = i2s_rx(sys_clk_freq=sys_clk_freq, sclk_freq=sclk_freq)
    sim = Simulator(dut)

    samples = [(C(i << 14, 32) ) for i in range(32)]

    def process():
        sample_in = 0
        for word in samples:
            for i in range(32):
                while (yield ~(dut.sclk)):
                    yield Tick()
                yield dut.sdin.eq(word[31 - i])

                while (yield (dut.sclk)):
                    yield Tick()
                if (yield dut.source.valid):
                    yield dut.source.ready.eq(1)
                    sample_out = (yield dut.source.data)
                    yield Tick()
                    yield dut.source.ready.eq(0)
            assert sample_in == sample_out, f"Expected {sample_in}, got: {sample_out}"
            sample_in += 1

    sim.add_process(process)
    sim.add_clock(1 / sys_clk_freq)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()


def main():
    # tx_tb()
    rx_tb()


if __name__ == "__main__":
    main()
