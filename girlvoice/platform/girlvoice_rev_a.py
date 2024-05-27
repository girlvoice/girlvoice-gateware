import os
import subprocess
from amaranth import *
from amaranth.build import *
from amaranth.vendor import LatticePlatform

from amaranth_boards.resources import *

__all__ = ["GirlvoiceRevAPlatform"]

class GirlvoiceRevAPlatform(LatticePlatform):
    device = "LIFCL-40"
    package = "SG72"
    speed = "8"
    default_clk = "clk12"

    resources = [
        Resource("clk12", 0, Pins("11", dir="i"),
            Clock(12e6), Attrs(IO_TYPE="LVCMOS18H")),


        I2CResource(0,
            scl="44", sda="42", attrs=Attrs(IO_TYPE="LVCMOS33")
        ),
        *SPIFlashResources(0,
            cs_n="56", clk="59", copi="57", cipo="51", wp_n="55", hold_n="52",
            attrs=Attrs(IO_TYPE="LVCMOS33")
        ),
        # SPIResource(0,
        #     cs_n="5", clk="6", copi="7", reset="8", conn=("ips", 0),
        #     attrs=Attrs(IO_TYPE="LVCMOS33")
        # ),

        Resource("pwr_en", 0, Pins("28", dir="o"), Attrs(IO_TYPE="LVCMOS18H")),

        Resource("btn_pwr", 0, Pins("27", dir="i"), Attrs(IO_TYPE="LVCMOS18H")),
        Resource("button_up", 0, Pins("19", dir="i", invert=True), Attrs(IO_TYPE="LVCMOS18")),
        Resource("button_down", 0, Pins("20", dir="i", invert=True), Attrs(IO_TYPE="LVCMOS18")),

        Resource("aux_clk", 0, Pins("MCLK", dir="o", conn=("aux_i2s", 0)), Attrs(IO_TYPE="LVCMOS18")),
        Resource("aux_dout", 0, Pins("SDOUT", dir="o", conn=("aux_i2s", 0)), Attrs(IO_TYPE="LVCMOS18")),
        Resource("aux_din", 0, Pins("SDIN", dir="i", conn=("aux_i2s", 0)), Attrs(IO_TYPE="LVCMOS18")),

        Resource("led", 0, Pins("13", dir="o"), Attrs(IO_TYPE="LVCMOS18H")),

        Resource("mic", 0,
            Subsignal("clk", Pins("SCLK", dir="o", conn=("mic_i2s", 0)), Attrs(IO_TYPE="LVCMOS18H")),
            Subsignal("data", Pins("SDIN", dir="i", conn=("mic_i2s", 0)), Attrs(IO_TYPE="LVCMOS18H")),
            Subsignal("lrclk", Pins("LRCLK", dir="o", conn=("mic_i2s", 0)), Attrs(IO_TYPE="LVCMOS18H")),
        ),

        Resource("amp", 0,
            Subsignal("clk", Pins("SCLK", dir="o", conn=("amp_i2s", 0)), Attrs(IO_TYPE="LVCMOS18H")),
            Subsignal("data", Pins("SDIN", dir="o", conn=("amp_i2s", 0)), Attrs(IO_TYPE="LVCMOS18H")),
            Subsignal("lrclk", Pins("LRCLK", dir="o", conn=("amp_i2s", 0)), Attrs(IO_TYPE="LVCMOS18H")),
            Subsignal("en", Pins("ENABLE", dir="o", conn=("amp_i2s", 0)), Attrs(IO_TYPE="LVCMOS18H")),
        ),

    ]

    connectors = [
        Connector("usb", 0, {
            "USB_DP"    : "41",
            "USB_DN"    : "43",
            "USB_RX1_p" : "57",
            "USB_RX1_n" : "59",
            "USB_RX2_p" : "56",
            "USB_RX2_n" : "51",
            "USB_SBU1"  : "60",
            "USB_SBU2"  : "58",
        }),
        Connector("ips", 0, "- 36 - - 46 53 48 45 - - - 15 16 42 44"),

        Connector("mic_i2s", 0, {
            "LRCLK": "23",
            "SCLK": "24",
            "SDIN": "25",
        }),
        Connector("amp_i2s", 0, {
            "LRCLK": "30",
            "SCLK": "31",
            "SDIN": "33",
            "ENABLE": "34",
            "INT": "37",
        }),
        # Connector("aux_i2s", 0, {
        #     "MCLK": "22",
        #     "SDIN": "10",
        #     "SDOUT": "27",
        # })

    ]


    def toolchain_program(self, products, name):
        ecpprog = os.environ.get("ECPPROG", "ecpprog")
        with products.extract("{}.bit".format(name)) as bitstream_filename:
            if self.toolchain == "radiant":
                bitstream_filename = f"build/impl/{name}_impl.bit"
            subprocess.check_call(ecpprog, "-S", bitstream_filename)

if __name__ == "__main__":
    p: Platform = GirlvoiceRevAPlatform()

    m = Module()

    count = Signal(24)
    m.d.sync += count.eq(count + 1)
    m.d.comb += p.request("led", 0).o.eq(count[-1])
    m.d.comb += p.request("pwr_en", 0).o.eq(1)

    p.build(m)