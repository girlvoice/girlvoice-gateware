from migen import *
from litex.gen import *
from litex.soc.interconnect import wishbone

_layout = [
    ("offset", "adr_width", DIR_M_TO_S),
    ("rdata", "data_width", DIR_S_TO_M),
    ("wdata", "data_width", DIR_M_TO_S),
    ("wr_rdn", 1, DIR_M_TO_S),
    ("request", 1, DIR_M_TO_S),
    ("ready", 1, DIR_S_TO_M),
    ("rdata_valid", 1, DIR_S_TO_M),
]


class Interface(Record):
    def __init__(self, data_width=32, adr_width=32):
        self.data_width = data_width
        self.adr_width = adr_width
        Record.__init__(
            self,
            set_layout_parameters(
                _layout,
                adr_width=self.adr_width,
                data_width=self.data_width,
            ),
        )


class LMMItoWishbone(LiteXModule):
    def __init__(self):
        # Downscaling bus to 8 bit addr and data for Lattice MMI
        self.wishbone = wishbone.Interface(
            data_width=32, adr_width=32, addressing="byte"
        )
        self.lmmi = Interface(data_width=8, adr_width=8)
        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act(
            "IDLE",
            If(
                self.wishbone.cyc & self.wishbone.stb,
                self.lmmi.wdata.eq(self.wishbone.dat_w),
                self.lmmi.request.eq(1),
                self.lmmi.wr_rdn.eq(self.wishbone.we),
                self.lmmi.offset.eq(self.wishbone.adr[4:]),
                If(
                    self.wishbone.we,
                    If(
                        self.lmmi.ready,
                        self.wishbone.ack.eq(1),
                        NextState("WRITE-WAIT"),
                    ),
                ).Else(NextState("READ-WAIT")),
            ),
        )
        fsm.act("WRITE-WAIT", self.wishbone.ack.eq(1), NextState("IDLE"))
        fsm.act(
            "READ-WAIT",
            If(
                self.lmmi.rdata_valid,
                self.wishbone.dat_r.eq(self.lmmi.rdata),
                self.wishbone.ack.eq(1),
                NextState("IDLE"),
            ),
        )


def main():
    dut = LMMItoWishbone()

    def tb():
        yield dut.lmmi.ready.eq(1)
        yield
        yield from dut.wishbone.write(adr=0x81000000, dat=0xDC)
        yield
        yield from dut.wishbone.write(adr=0x81000010, dat=0xBE)
        yield
        # yield from dut.wishbone.read(adr=0x16)

    run_simulation(dut, tb(), vcd_name="lmmi.vcd")


if __name__ == "__main__":
    main()
