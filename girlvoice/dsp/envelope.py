#!/usr/bin/env python3
import os
import math
import numpy as np
from scipy import signal
import matplotlib.pyplot as plt
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream

from amaranth.sim import Simulator


class EnvelopeFollower(wiring.Component):

    def __init__(self, sample_width=24, attack=0.75):
        self.fraction_width = sample_width - 1
        self.attack_p = C(int(attack * (2**(self.fraction_width))), signed(sample_width))
        self.attack_comp = C(int((1 - attack) * (2**(self.fraction_width))), signed(sample_width))
        print(bin(self.attack_p.value))
        self.sample_width = sample_width
        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })

    def elaborate(self, platform):
        m = Module()

        mac_width = self.sample_width*2

        mult_x = Signal(signed(mac_width))
        mult_y = Signal(signed(mac_width))
        acc = Signal(signed(mac_width))

        x = Signal(signed(self.sample_width))
        y = Signal(signed(self.sample_width))

        attack_complement = self.attack_comp


        m.d.comb += [mult_x.eq(attack_complement * abs(x)),
                     mult_y.eq(self.attack_p * y),
                     acc.eq(mult_x + mult_y)]
        with m.If(self.sink.valid):
            m.d.sync += x.eq(self.sink.payload)
            m.d.sync += self.sink.ready.eq(0)
        with m.Else():
            m.d.sync += self.sink.ready.eq(1)
            m.d.sync += y.eq(acc >> self.fraction_width)

            m.d.sync += self.source.valid.eq(1)
        with m.If(self.source.ready):
            m.d.comb += self.source.payload.eq(y)

        return m


# Testbench ----------------------------------------

async def stream_get(ctx, stream):
    ctx.set(stream.ready, 1)
    payload, = await ctx.tick().sample(stream.payload).until(stream.valid)
    ctx.set(stream.ready, 0)
    return payload

async def stream_put(ctx, stream, payload):
    ctx.set(stream.valid, 1)
    ctx.set(stream.payload, payload)
    await ctx.tick().until(stream.ready)
    ctx.set(stream.valid, 0)

def run_sim():
    clk_freq = 12e6
    bit_width = 32
    dut = EnvelopeFollower(sample_width=bit_width)

    duration = 1
    fs = 48000
    start_freq = 1
    end_freq = 10000
    test_sig_freq = 5000
    num_samples = duration * fs
    t = np.linspace(0, duration, num_samples)
    input_samples = signal.sawtooth(2 * np.pi * test_sig_freq * t) * t * 0.25
    input_samples *= (2**(bit_width - 1))

    input_samples = np.flip(input_samples)
    input_samples[0:4800] = 0
    print([int(x) for x in input_samples[:5]])
    output_samples = []
    async def tb(ctx):
        for sample in input_samples:
            output_samples.append(await stream_get(ctx, dut.source))
            await stream_put(ctx, dut.sink, int(sample))
            await ctx.tick()
        #print(output_samples)

    sim = Simulator(dut)
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        plt.plot(t, input_samples, alpha=0.5, label="Input")
        plt.plot(t, output_samples, alpha=0.5, label="Output")
        plt.xlabel('time ')
        plt.title('Envelope Follower')
        plt.grid(True)
        # plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
        plt.legend()
        plt.savefig(f"{type(dut).__name__}.png")
        plt.show()




if __name__ == "__main__":
    run_sim()