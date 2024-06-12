from litex.build.generic_platform import *
from litex.build.lattice import LatticeNexusPlatform
from litex.build.lattice.programmer import IceStormProgrammer


# IOs ----------------------------------------------------------------------------------------------

_io = [
    ("clk12", 0, Pins("11"), IOStandard("LVCMOS18H")),

    ("serial", 0,
        Subsignal("rx", Pins("41"), IOStandard("LVCMOS33")),
        Subsignal("tx", Pins("43"), IOStandard("LVCMOS33")),
    ),
    ("led", 0, Pins("13"), IOStandard("LVCMOS18H")),

    ("btn_pwr", 0, Pins("27"), IOStandard("LVCMOS18H")),
    ("btn_up", 0, Pins("19"), IOStandard("LVCMOS18H")),
    ("btn_down", 0, Pins("20"), IOStandard("LVCMOS18H")),

    ("pwr_en", 0, Pins("28"), IOStandard("LVCMOS18H")),

    ("spiflash", 0,
        Subsignal("cs_n", Pins("56")),
        Subsignal("clk",  Pins("59")),
        Subsignal("mosi", Pins("57")),
        Subsignal("miso", Pins("51")),
        Subsignal("wp",   Pins("55")),
        Subsignal("hold", Pins("52")),
        IOStandard("LVCMOS33")
    ),


    ("i2c", 0,
        Subsignal("scl", Pins("44")),
        Subsignal("sda", Pins("42")),
        IOStandard("LVCMOS33"), Misc("PULLMODE=NONE")
    ),

    ("aux_mclk", 0, Pins("22"), IOStandard("LVCMOS18H")),

    ("amp", 0,
        Subsignal("en", Pins("34")),
        Subsignal("bclk", Pins("31")),
        IOStandard("LVCMOS18H")
    ),

    ("tp_rstn", 0, Pins("15"), IOStandard("LVCMOS18H")),
]


# Platform -----------------------------------------------------------------------------------------

class Platform(LatticeNexusPlatform):
    default_clk_name   = "clk12"
    default_clk_period = 1e9/12e6

    def __init__(self, device="LIFCL-17-8SG72C", toolchain="radiant", **kwargs):

        assert device in ["LIFCL-17-8SG72C", "LIFCL-40-8SG72C"]
        LatticeNexusPlatform.__init__(self, device, _io, toolchain=toolchain, **kwargs)

    def request(self, *args, **kwargs):
        return LatticeNexusPlatform.request(self, *args, **kwargs)

    def create_programmer(self, mode = "flash", prog="iceprog"):
        assert mode in ["flash"]
        assert prog in ["iceprog"]

        if prog == "iceprog":
            return IceStormProgrammer()
