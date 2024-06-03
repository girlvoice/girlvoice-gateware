from amaranth import *
from amaranth.build import *
from amaranth.build.plat import Platform

from girlvoice.platform.girlvoice_rev_a import GirlvoiceRevAPlatform
from girlvoice.platform.nexus_utils.pll import NXPLL
from girlvoice.io.i2s import i2s_rx, i2s_tx

class GirlTop(Elaboratable):

    def elaborate(self, platform:Platform):
        m = Module()

        pll_lock = Signal()

        amp = platform.request("amp", 0)
        mic = platform.request("mic", 0)

        dac_din = amp.data
        dac_sd_mode_n = amp.en

        adc_dout = mic.data

        global_lr_clk = Signal()
        global_bclk = Signal()

        amp_lr_clk = amp.lrclk
        amp_bclk = amp.clk
        mic_lr_clk = mic.lrclk
        mic_bclk = mic.clk

        m.d.comb += amp_lr_clk.o.eq(global_lr_clk)
        m.d.comb += amp_bclk.o.eq(global_bclk)
        m.d.comb += mic_lr_clk.o.eq(global_lr_clk)
        m.d.comb += mic_bclk.o.eq(global_bclk)
        # sclk_i = platform.request("sclk_i", 0)

        m.domains.sync = cd_sync = ClockDomain("sync", local=True)

        m.submodules.pll = NXPLL(
            platform.request("clk12", dir="i").i,
            clkin_freq=12e6,
            cd_out=cd_sync,
            clkout=cd_sync.clk,
            clkout_freq=24e6)
        platform.add_clock_constraint(cd_sync.clk, 24e6)

        m.submodules.i2s_rx = rx = i2s_rx(sys_clk_freq=24e6, sclk_freq=4e6, sample_width=24)

        m.d.comb += global_bclk.eq(rx.sclk)
        m.d.comb += global_lr_clk.eq(rx.lrclk)
        m.d.comb += dac_din.o.eq(adc_dout.i)

        m.d.comb += dac_sd_mode_n.o.eq(1)

        return m

if __name__ == "__main__":
    p = GirlvoiceRevAPlatform()

    p.build(GirlTop(), do_program=False)
