from amaranth import *
from amaranth.build import *
from amaranth.build.plat import Platform

from girlvoice.platform.lifcl_evn import LIFCLEVNPlatform
from girlvoice.platform.nexus_utils.pll import NXPLL
from girlvoice.i2s import i2s_rx, i2s_tx

class GirlTop(Elaboratable):

    def elaborate(self, platform:Platform):
        m = Module()

        ## Clock Defs

        sync_freq = 64e6
        bclk_freq = 4e6

        clk_sync = Signal()
        m.domains.sync = cd_sync = ClockDomain("sync")

        clkin = platform.request("clk12", dir="i").i

        m.submodules.pll = NXPLL(
            clkin=clkin,
            clkin_freq=12e6,
            cd_out=cd_sync,
            clkout=clk_sync,
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
        m.submodules.i2s_rx = rx = i2s_rx(sys_clk_freq=64e6, sclk_freq=4e6, sample_width=18)

        adc = platform.request("adc", 0)
        adc_dout = adc.data
        adc_lr_clk = adc.lrclk
        adc_bclk = adc.bclk
        sclk_i = adc.sclk

        m.d.comb += adc_lr_clk.o.eq(rx.lrclk)
        m.d.comb += adc_bclk.o.eq(bclk)
        m.d.comb += rx.sclk.eq(bclk)
        m.d.comb += rx.sdin.eq(adc_dout.i)

        adc_sample_out = Signal(18)
        # m.d.comb += adc_sample_out.eq(rx.source.data >> 6)

        clk_sig = Signal()
        m.d.comb += sclk_i.o.eq(clk_sig)
        m.d.sync += clk_sig.eq(~clk_sig)

        ## TX to DAC
        m.submodules.i2s_tx = tx = i2s_tx(sys_clk_freq=64e6, sclk_freq=4e6, sample_width=18)

        amp = platform.request("amp", 0)
        amp_lr_clk = amp.lrclk
        amp_bclk = amp.clk
        dac_din = amp.data
        dac_sd_mode_n = amp.en

        m.d.comb += dac_sd_mode_n.o.eq(1)
        m.d.comb += amp_lr_clk.o.eq(tx.lrclk)
        m.d.comb += amp_bclk.o.eq(bclk)
        m.d.comb += dac_din.o.eq(tx.sdout)

        shift_reg = Signal(18)

        m.d.comb += tx.sink.data.eq(rx.source.data)
        m.d.comb += tx.sink.valid.eq(1)
        m.d.comb += tx.sclk.eq(bclk)
        m.d.comb += rx.source.ready.eq(tx.sink.ready)

        m.d.comb += platform.request("led", 0).o.eq(rx.source.data.xor())

        return m

if __name__ == "__main__":
    p = LIFCLEVNPlatform(VCCIO6="1V8")

    prototype_resources = [
        Resource("mic", 0,
            Subsignal("clk", Pins("RASP_IO06", dir="o", conn=("RASP", 0)), Attrs(IO_TYPE="LVCMOS18")),
            Subsignal("data", Pins("RASP_IO05", dir="i", conn=("RASP", 0)), Attrs(IO_TYPE="LVCMOS18")),
            Subsignal("lrclk", Pins("RASP_IO19", dir="o", conn=("RASP", 0)), Attrs(IO_TYPE="LVCMOS18")),
            Subsignal("sel", Pins("RASP_IO26", dir="o", conn=("RASP", 0)), Attrs(IO_TYPE="LVCMOS18"))
        ),

        Resource("amp", 0,
            Subsignal("clk", Pins("RASP_IO03", dir="o", conn=("RASP", 0)), Attrs(IO_TYPE="LVCMOS18")),
            Subsignal("data", Pins("RASP_IO02", dir="o", conn=("RASP", 0)), Attrs(IO_TYPE="LVCMOS18")),
            Subsignal("lrclk", Pins("RASP_IO04", dir="o", conn=("RASP", 0)), Attrs(IO_TYPE="LVCMOS18")),
            Subsignal("en", Pins("RASP_IO17", dir="o", conn=("RASP", 0)), Attrs(IO_TYPE="LVCMOS18")),
        ),
    ]

    pmod_adc = [
        Resource("adc", 0,
            Subsignal("sclk", Pins("1", dir="o", conn=("pmod", 0)), Attrs(IO_TYPE="LVCMOS33")),
            Subsignal("data", Pins("3", dir="i", conn=("pmod", 0)), Attrs(IO_TYPE="LVCMOS33")),
            Subsignal("lrclk", Pins("2", dir="o", conn=("pmod", 0)), Attrs(IO_TYPE="LVCMOS33")),
            Subsignal("bclk", Pins("4", dir="o", conn=("pmod", 0)), Attrs(IO_TYPE="LVCMOS33")),
        ),
    ]
    p.add_resources(prototype_resources)
    p.add_resources(pmod_adc)
    p.build(GirlTop(), do_program=False)
