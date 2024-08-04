from scipy import signal

from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.sim import Simulator

import girlvoice.stream as stream


class BandpassFIR(wiring.Component):

    def __init__(self, cutoff_freq, passband_width, filter_order=24, integer_width=16, fraction_width=16, samplerate=48e3):
        cutoff_freq = cutoff_freq / samplerate
        passband_width = passband_width / samplerate
        band_edges = [cutoff_freq - passband_width/2, cutoff_freq + passband_width / 2]

        super().__init__({
            "sink": In(stream.StreamSignature(integer_width)),
            "source": Out(stream.StreamSignature(integer_width))
        })

        taps = signal.firwin(filter_order, cutoff=band_edges, fs=samplerate, pass_zero="bandpass", window='hamming')

        self.integer_width = integer_width
        self.fraction_width = fraction_width
        assert integer_width <= fraction_width, f"Bitwidth {integer_width} must not exceed {fraction_width}"
        self.taps = taps_fp = [int(x * 2**fraction_width) for x in taps]

    def elaborate(self, platform):
        m = Module()

        width = self.integer_width + self.fraction_width
        taps = Array([Const(x, width) for x in self.taps])

        ring_buf = Array([Signal(width) for _ in range(len(self.taps))])

        pipeline_dsp = True
        if pipeline_dsp:
            idx = Signal(range(len(self.taps)))
            acc = Signal(width)
            with m.FSM():
                with m.State("LOAD"):
                    m.d.comb += self.sink.ready.eq(1)
                    with m.If(self.sink.valid):
                        m.d.sync += [ring_buf[i + 1].eq(ring_buf[i]) for i in range(len(self.taps) - 1)]
                        m.d.sync += ring_buf[0].eq(self.sink.data)
                        m.d.sync += idx.eq(0)
                        m.next = "CALC"
                with m.State("CALC"):
                    m.d.sync += idx.eq(idx + 1)
                    m.d.sync += acc.eq(acc + ((ring_buf[idx] * taps[idx]) >> self.fraction_width))
                    with m.If(idx == len(self.taps) - 1):
                        m.d.sync += self.source.data.eq(acc)
                        m.d.sync += self.source.valid.eq(1)
                        m.next = "LOAD"
        else:
            with m.If(self.sink.valid):
                m.d.sync += [ring_buf[i + 1].eq(ring_buf[i]) for i in range(len(self.taps) - 1)]
                m.d.sync += ring_buf[0].eq(self.sink.data)

            m.d.comb += self.source.valid.eq(self.sink.valid)

            y = sum((ring_buf[i] * taps[i]) >> self.fraction_width for i in range(len(self.taps)))
            m.d.comb += self.source.data.eq(y)

        return m


# Testbench ----------------------------------------

def tb():
    pass

def main():
    clk_freq = 12e6
    dut = BandpassFIR(1e3, 500)
    sim = Simulator(dut)

    sim.add_clock(1/48e3)

if __name__ == "__main__":
    tb()