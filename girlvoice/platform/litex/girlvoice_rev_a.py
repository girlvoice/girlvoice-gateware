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
    ("user_led", 0, Pins("13"), IOStandard("LVCMOS18H")),

    ("user_btn", 0, Pins("9"), IOStandard("LVCMOS18H")),
    ("gsrn", 1, Pins("19"), IOStandard("LVCMOS18H")),
    ("user_btn", 2, Pins("20"), IOStandard("LVCMOS18")),

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
    )
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
