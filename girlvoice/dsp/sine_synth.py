import os
import numpy as np
import matplotlib.pyplot as plt
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream
from amaranth.sim import Simulator

from girlvoice.stream import stream_get
class StaticSineSynth(wiring.Component):

    def __init__(self, frequency, fs, sample_width):

        assert frequency <= fs/2

        super().__init__({
            "en": In(1),
            "source": Out(stream.Signature(signed(sample_width), always_valid=True))
        })

        self.sample_width = sample_width
        self.frequency = frequency
        self.fs = fs

        self.N = int(self.fs / self.frequency)
        print(f"Target synth freq: {self.frequency}, actual: {fs / self.N}")

    def elaborate(self, platform):
        m = Module()

        N = self.N

        t = np.linspace(0, 2*np.pi, N)
        y = np.sin(t)
        y_norm = y * (2**(self.sample_width - 1))
        print(t)
        print(y)
        print(y_norm)
        ring = Array([C(int(y_i), signed(self.sample_width)) for y_i in y_norm])

        idx = Signal(range(N), reset=0)

        with m.If(self.en):
            m.d.comb += self.source.payload.eq(ring[idx])
            with m.If(self.source.ready):
                with m.If(idx < N):
                    m.d.sync += idx.eq(idx+1)
                with m.Else():
                    m.d.sync += idx.eq(0)

        return m

def run_sim():
    clk_freq = 60e6
    bit_width = 16
    target_freq = 1000
    fs = 48000
    duration = 1
    dut = StaticSineSynth(frequency=target_freq, fs=fs, sample_width=bit_width)

    num_samples = fs * duration

    t = np.linspace(0, duration, num_samples)
    output_samples = []
    async def tb(ctx):
        ctx.set(dut.en, 1)
        for _ in range(num_samples):
            output_samples.append(await stream_get(ctx, dut.source))
            await ctx.tick()

    sim = Simulator(dut)
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        # bode_plot(fs, duration, end_freq, input_samples, output_samples)
        ax2 = plt.subplot(111)
        ax2.plot(t, output_samples, alpha=0.5, label="Output")
        ax2.set_xlabel('time (s)')
        plt.title('Sine Synth')
        plt.grid(True)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
        plt.legend()
        # plt.savefig(f"{type(dut).__name__}.png")
        plt.show()




if __name__ == "__main__":
    run_sim()

