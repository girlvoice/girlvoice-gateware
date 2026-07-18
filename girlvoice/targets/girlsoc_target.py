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
        self.source_clk_freq = 24e6
        self.sync_freq = 60e6
        self.audio_clk_freq = 24.576e6
        self.fast_clk_freq = 2 * self.sync_freq
        self.soc = GirlvoiceSoc(audio_clk_freq=self.audio_clk_freq)

    def elaborate(self, platform:Platform):
        m = Module()

        ## Clock Defs
        clkin = platform.request("clk24", dir="i").i
        m.domains.clk24 = cd_clk24 = ClockDomain("clk24")
        m.d.comb += cd_clk24.clk.eq(clkin)
        platform.add_clock_constraint(cd_clk24.clk, self.source_clk_freq)

        m.domains.sync = cd_sync = ClockDomain("sync")
        m.domains.fast = cd_fast = ClockDomain("fast")
        m.domains.audio = cd_audio = ClockDomain("audio")

        m.submodules.pll_core = pll_core = NXPLL(
            clkin=clkin,
            clkin_freq=self.source_clk_freq,
            cd_out=cd_fast,
            clkout=cd_fast.clk,
            clkout_freq=self.fast_clk_freq)

        pll_core.create_clkout(cd_sync, self.sync_freq)

        platform.add_clock_constraint(cd_sync.clk, self.sync_freq)
        platform.add_clock_constraint(cd_fast.clk, self.fast_clk_freq)

        m.submodules.pll_audio = pll_audio = NXPLL(
            clkin=clkin,
            clkin_freq=self.source_clk_freq,
            cd_out=cd_audio,
            clkout=cd_audio.clk,
            clkout_freq=self.audio_clk_freq,
            enable_fractional_synth=True,
        )
        platform.add_clock_constraint(cd_audio.clk, self.audio_clk_freq)

        codec_mclk_port = platform.request("aux_clk")
        m.d.comb += codec_mclk_port.o.eq(cd_audio.clk)

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
