from migen import *
from litex.gen import *

_layout = [
    ("offset",  "adr_width",    DIR_M_TO_S),
    ("rdata",   "data_width",   DIR_S_TO_M),
    ("wdata",   "data_width",   DIR_M_TO_S),
    ("wr_rdn",            1,    DIR_M_TO_S),
    ("request",           1,    DIR_M_TO_S),
    ("ready",             1,    DIR_S_TO_M),
    ("rdata_valid",       1,    DIR_S_TO_M),
]

class Interface(Record):
    def __init__(self, data_width=32, adr_width=32):
        self.data_width = data_width
        self.adr_width  = adr_width
        Record.__init__(self, set_layout_parameters(_layout,
            adr_width  = self.adr_width,
            data_width = self.data_width,
        ))
