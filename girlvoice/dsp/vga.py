#!/usr/bin/env python
import os
import numpy as np
import matplotlib.pyplot as plt
import numpy as np
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream
from amaranth.sim import Simulator

from girlvoice.stream import stream_get, stream_put
from girlvoice.dsp.tdm_slice import TDMMultiply
from girlvoice.dsp.utils import generate_sine

class VariableGainAmp(wiring.Component):
    def __init__(self, carrier_width, modulator_width, mult_slice:TDMMultiply = None):
        self.modulator_width = modulator_width
        self.carrier_width = carrier_width

        if mult_slice is not None:
            assert mult_slice.sample_width == self.modulator_width
            assert mult_slice.sample_width == self.carrier_width
            self.mult = mult_slice
        else:
            self.mult = None
        super().__init__({
            "carrier": In(stream.Signature(signed(carrier_width))),
            "modulator": In(stream.Signature(signed(modulator_width))),
            "source": Out(stream.Signature(signed(carrier_width)))
        })

    def elaborate(self, platform):
        m = Module()

        if self.mult is None:
            i_valid = Signal()

            product = Signal(signed(self.carrier_width + self.modulator_width))
            # product.attrs["syn_multstyle"] = "block_mult"

            m.d.comb += product.eq(self.carrier.payload * self.modulator.payload)
            m.d.comb += i_valid.eq(self.modulator.valid & self.carrier.valid)

            with m.If(i_valid & (~self.source.valid | self.source.ready)):
                m.d.sync += self.source.payload.eq(product >> (self.modulator_width - 1))
                m.d.sync += self.source.valid.eq(1)
                m.d.comb += self.carrier.ready.eq(1)
                m.d.comb += self.modulator.ready.eq(1)
            with m.Elif(self.source.ready):
                m.d.sync += self.source.valid.eq(0)
        else:
            # m.submodules.mult = self.mult
            product = self.mult.source
            mult_i_a, mult_i_b, mult_ready, mult_valid = self.mult.get_next_thread_ports()

            with m.FSM():
                with m.State("LOAD"):
                    with m.If(self.source.ready):
                        m.d.sync += self.source.valid.eq(0)

                    with m.If(self.modulator.valid & self.carrier.valid
                              & mult_ready & ~self.source.ready):
                        m.d.comb += self.modulator.ready.eq(1)
                        m.d.comb += self.carrier.ready.eq(1)

                        m.d.sync += mult_i_a.eq(self.modulator.payload)
                        m.d.sync += mult_i_b.eq(self.carrier.payload)

                        m.next = "WAIT"
                with m.State("WAIT"):
                    with m.If(mult_valid):
                        m.d.sync += self.source.payload.eq(product >> (self.modulator_width - 1))
                        m.d.sync += self.source.valid.eq(1)
                        m.next = "LOAD"

        return m


def run_sim():
    clk_freq = 60e6
    sample_width = 16 # Number of 2s complement bits
    fs = 48000

    mult = TDMMultiply(sample_width=sample_width, num_threads=2)

    dut = VariableGainAmp(
        carrier_width=sample_width,
        modulator_width=sample_width,
        mult_slice=mult
    )

    duration = .25
    test_freq = 10
    (t, input_samples) = generate_sine(duration, fs, test_freq, sample_width)
    output_samples = np.zeros(int(duration * fs))
    async def tb(ctx):
        samples_processed = 0
        await ctx.tick()
        ctx.set(dut.carrier.payload, 2**(sample_width - 2))
        ctx.set(dut.carrier.valid, 1)
        await ctx.tick()
        for sample in input_samples:
            await stream_put(ctx, dut.modulator, int(sample))
            output_samples[samples_processed] = (await stream_get(ctx, dut.source))
            await ctx.tick()
            samples_processed += 1
            if samples_processed % 1000 == 0:
                print(f"{samples_processed}/{len(t)} Samples processed")

    sim = Simulator(dut)
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        print(output_samples[-50:])
        ax2 = plt.subplot(121)
        ax2.plot(t, input_samples, alpha=0.5, label="Input")
        ax2.plot(t, output_samples, alpha=0.5, label="Output")
        ax2.set_xlabel('Time (s)')
        ax2.set_ylabel("Amplitude")
        plt.title('Variable Gain Amplifier')
        plt.grid(True)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
        # plt.savefig(f"{type(dut).__name__}.png")
        plt.show()

if __name__ == "__main__":
    run_sim()