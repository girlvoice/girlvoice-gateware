#!/usr/bin/env python
from amaranth import *
from amaranth.build import *
from amaranth.build.plat import Platform
from girlvoice.soc.vendor.luna_soc import top_level_cli
# from luna_soc import top_level_cli

from girlvoice.platform.girlvoice_rev_a import GirlvoiceRevAPlatform
from girlvoice.platform.nexus_utils.pll import NXPLL
from girlvoice.io.i2s import i2s_rx, i2s_tx
from girlvoice.dsp.bandpass_iir import BandpassIIR
import girlvoice.dsp.vocoder as vocoder

from girlvoice.soc.girlvoice_soc import GirlvoiceSoc

class GirlTop(Elaboratable):

    def __init__(self):
        self.soc = GirlvoiceSoc()

    def elaborate(self, platform:Platform):
        m = Module()

        ## Clock Defs

        sync_freq = 60e6
        bclk_freq = 4e6

        clkin = platform.request("clk12", dir="i").i
        m.domains.clk12 = cd_clk12 = ClockDomain("clk12")
        m.d.comb += cd_clk12.clk.eq(clkin)
        platform.add_clock_constraint(cd_clk12.clk, 12e6)

        m.domains.sync = cd_sync = ClockDomain("sync")

        m.submodules.pll = pll = NXPLL(
            clkin=clkin,
            clkin_freq=12e6,
            cd_out=cd_sync,
            clkout=cd_sync.clk,
            clkout_freq=sync_freq)
        platform.add_clock_constraint(cd_sync.clk, sync_freq)

        ## Add SoC
        m.submodules.soc = self.soc

        ## Power On/Off
        pwr_button = platform.request("btn_pwr", 0).i
        pwr_en = platform.request("pwr_en", 0)

        pwr_on = Signal(init=1)
        m.d.comb += pwr_en.o.eq(pwr_on)

        btn_last = Signal(init=1)
        btn_rising = Signal()
        m.d.sync += btn_last.eq(pwr_button)
        m.d.sync += btn_rising.eq(pwr_button & ~btn_last)


        with m.If(btn_rising):
            m.d.sync += pwr_on.eq(0)

        return m

if __name__ == "__main__":
    p = GirlvoiceRevAPlatform(toolchain="Oxide")

    top_level_cli(GirlTop())
    # p.build(GirlTop(), do_program=False, use_radiant_docker=False)
