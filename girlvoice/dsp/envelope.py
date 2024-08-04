import os
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream

from amaranth.sim import Simulator


class EnvelopeFollower(wiring.Component):

    def __init__(self, sample_width=24, attack=0.5):

        self.attack_p = C(attack * 2**sample_width, sample_width)
        self.sample_width = sample_width
        super().__init__({
            "sink": In(stream.Interface(signed(sample_width))),
            "source": Out(stream.Interface(signed(sample_width)))
        })

    def elaborate(self, platform):
        m = Module()

        y = Signal(signed(self.sample_width))

        attact_comp = 2**self.sample_width - self.attack_p

        abs_x = abs(self.sink.payload)

        m.d.sync += self.sink.ready.eq(self.source.ready)
        with m.If(self.sink.valid):
            m.d.sync += y.eq((self.attack_p * y) + (attact_comp * abs_x))

        m.d.comb += self.source.valid.eq(1)
        with m.If(self.source.ready):
            m.d.sync += self.source.payload.eq(y)

        return m


def tb():
    pass

def run_sim():
    clk_freq = 12e6

    dut = EnvelopeFollower()
    sim = Simulator()

    sim.add_clock(clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()



if __name__ == "__main__":
    run_sim()