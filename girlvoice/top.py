from amaranth import *
from amaranth.build import *
from amaranth.build.plat import Platform
from amaranth_boards.icebreaker import ICEBreakerPlatform

from i2s import i2s_rx, i2s_tx

class GirlTop(Elaboratable):
    def __init__(self) -> None:
        pass
    def elaborate(self, platform:Platform):
        m = Module()

        pll_lock = Signal()

        dac_din = platform.request("dac_din", 0)
        dac_sd_mode_n = platform.request("dac_sd_n", 0)

        adc_dout = platform.request("adc_dout", 0)

        global_lr_clk = platform.request("lrclk", 0)
        global_bclk = platform.request("bclk")
        sclk_i = platform.request("sclk_i", 0)


        m.submodules.pll = Instance(
            "SB_PLL40_PAD",
            p_DIVR = Const(0),
            p_DIVF = Const(63),
            p_DIVQ = Const(5),
            p_FILTER_RANGE = Const(1),
            p_FEEDBACK_PATH = "SIMPLE",
            p_DELAY_ADJUSTMENT_MODE_FEEDBACK = "FIXED",
            p_DELAY_ADJUSTMENT_MODE_RELATIVE = "FIXED",
            i_RESETB=1,
            i_PACKAGEPIN = platform.request("clk12", dir="-"),
            o_PLLOUTGLOBAL = ClockSignal("sync"),
            o_LOCK = pll_lock,

        )

        m.domains.sync = cd_sync = ClockDomain("sync", local=True)
        platform.add_clock_constraint(cd_sync.clk, 24e6)

        m.submodules.i2s_rx = rx = i2s_rx(sys_clk_freq=24e6, sclk_freq=4e6, sample_width=24)

        m.d.comb += global_bclk.o.eq(rx.sclk)
        m.d.comb += global_lr_clk.o.eq(rx.lrclk)
        m.d.comb += dac_din.o.eq(adc_dout.i)

        m.d.comb += sclk_i.o.eq(ClockSignal())
        m.d.comb += dac_sd_mode_n.o.eq(1)

        return m

if __name__ == "__main__":
    p = ICEBreakerPlatform()

    breadboard_dev = [
        Resource("adc_dout", 0, Pins("3", dir="i", conn=("pmod", 0)), Attrs(IO_STANDARD="SB_LVCMOS")),
        Resource("bclk", 0,  Pins("4", dir="o", conn=("pmod", 0)), Attrs(IO_STANDARD="SB_LVCMOS")),
        Resource("lrclk", 0, Pins("2", dir="o", conn=("pmod", 0)), Attrs(IO_STANDARD="SB_LVCMOS")),
        Resource("sclk_i", 0, Pins("1", dir="o", conn=("pmod",0)), Attrs(IO_STANDARD="SB_LVCMOS")),
        Resource("dac_din", 0, Pins("1", dir="o", conn=("pmod", 1)), Attrs(IO_STANDARD="SB_LVCMOS")),
        Resource("dac_sd_n", 0, Pins("2", dir="o", conn=("pmod", 1)), Attrs(IO_STANDARD="SB_LVCMOS")),

    ]

    p.add_resources(breadboard_dev)

    p.build(GirlTop(), do_program=True)
