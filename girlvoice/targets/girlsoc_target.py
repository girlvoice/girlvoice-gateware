#!/usr/bin/env python
from amaranth import *
from amaranth.build import *
from amaranth.build.plat import Platform
from girlvoice.soc.vendor.luna_soc import top_level_cli
# from luna_soc import top_level_cli

from girlvoice.platform.girlvoice_rev_a import GirlvoiceRevAPlatform
from girlvoice.platform.nexus_utils.pll import NXPLL

from girlvoice.soc.girlvoice_soc import GirlvoiceSoc

class GirlTop(Elaboratable):

    def __init__(self):
        self.soc = GirlvoiceSoc()

    def elaborate(self, platform:Platform):
        m = Module()

        ## Clock Defs

        source_clk_freq = 12e6
        sync_freq = 60e6
        fast_clk_freq = 2 * sync_freq


        clkin = platform.request("clk12", dir="i").i
        m.domains.clk12 = cd_clk12 = ClockDomain("clk12")
        m.d.comb += cd_clk12.clk.eq(clkin)
        platform.add_clock_constraint(cd_clk12.clk, source_clk_freq)

        m.domains.sync = cd_sync = ClockDomain("sync")
        m.domains.fast = cd_fast = ClockDomain("fast")

        m.submodules.pll = pll = NXPLL(
            clkin=clkin,
            clkin_freq=source_clk_freq,
            cd_out=cd_fast,
            clkout=cd_fast.clk,
            clkout_freq=fast_clk_freq)

        pll.create_clkout(cd_sync, sync_freq)

        platform.add_clock_constraint(cd_sync.clk, sync_freq)
        platform.add_clock_constraint(cd_fast.clk, fast_clk_freq)

        ## Add SoC
        m.submodules.soc = self.soc

        ## Power On/Off
        pwr_en = platform.request("pwr_en", 0)

        pwr_on = Signal(init=1)
        m.d.comb += pwr_en.o.eq(pwr_on)

        return m

if __name__ == "__main__":
    p = GirlvoiceRevAPlatform(toolchain="Oxide")

    top_level_cli(GirlTop())
    # p.build(GirlTop(), do_program=False, use_radiant_docker=False)
