from os import sync
from amaranth import *
from amaranth.build import *
from amaranth.build.plat import Platform

from girlvoice.platform.girlvoice_rev_a import GirlvoiceRevAPlatform
from girlvoice.platform.nexus_utils.pll import NXPLL
from girlvoice.io.i2s import i2s_rx, i2s_tx

class GirlTop(Elaboratable):

    def elaborate(self, platform:Platform):
        m = Module()


        ## Clock Defs

        sync_freq = 32e6
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

        clk_ratio = int(sync_freq // bclk_freq)
        clk_div = Signal(range(clk_ratio))

        bclk = Signal()
        with m.If(clk_div >= (clk_ratio - 1) // 2):
            m.d.sync += clk_div.eq(0)
            m.d.sync += bclk.eq(~bclk)
        with m.Else():
            m.d.sync += clk_div.eq(clk_div + 1)

        ## RX from ADC
        m.submodules.i2s_rx = rx = i2s_rx(sys_clk_freq=sync_freq, sclk_freq=bclk_freq, sample_width=24)

        adc = platform.request("mic", 0)

        adc_dout = adc.data
        adc_lr_clk = adc.lrclk
        adc_bclk = adc.clk
        # sclk_i = adc.sclk

        m.d.comb += adc_lr_clk.o.eq(rx.lrclk)
        m.d.comb += adc_bclk.o.eq(rx.sclk)
        m.d.comb += rx.sdin.eq(adc_dout.i)

        # adc_sclk = ClockDomain("adc_sclk")
        # m.domains += adc_sclk
        # pll.create_clkout(adc_sclk, 16e6)
        # m.d.comb += sclk_i.o.eq(adc_sclk.clk)

        ## TX to DAC
        m.submodules.i2s_tx = tx = i2s_tx(sys_clk_freq=sync_freq, sclk_freq=bclk_freq, sample_width=24)

        amp = platform.request("amp", 0)
        amp_lr_clk = amp.lrclk
        amp_bclk = amp.clk
        dac_din = amp.data
        dac_sd_mode_n = amp.en

        m.d.comb += dac_sd_mode_n.o.eq(1)
        m.d.comb += amp_lr_clk.o.eq(~tx.lrclk)
        m.d.comb += amp_bclk.o.eq(tx.sclk)
        m.d.comb += dac_din.o.eq(tx.sdout)


        m.d.comb += tx.sink.data.eq(rx.source.data)
        m.d.comb += rx.source.ready.eq(tx.sink.ready)
        m.d.comb += tx.sink.valid.eq(rx.source.valid)



        ## Power On/Off
        pwr_button = platform.request("btn_pwr", 0).i
        pwr_en = platform.request("pwr_en", 0)

        pwr_on = Signal(init=1)
        m.d.comb += pwr_en.o.eq(pwr_on)
        m.d.comb += platform.request("led", 0).o.eq(1)

        btn_last = Signal(init=1)
        btn_rising = Signal()
        m.d.sync += btn_last.eq(pwr_button)
        m.d.sync += btn_rising.eq(pwr_button & ~btn_last)


        with m.If(btn_rising):
            m.d.sync += pwr_on.eq(0)

        return m

if __name__ == "__main__":
    p = GirlvoiceRevAPlatform(toolchain="Radiant")

    p.build(GirlTop(), do_program=False, use_radiant_docker=True)
