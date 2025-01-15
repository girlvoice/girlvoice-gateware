#!/usr/bin/env python3
import os
import random
from tkinter import W
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream

from amaranth.sim import Simulator

class TDMMultiply(wiring.Component):
    def __init__(self, sample_width, threads):
        self.sample_width = sample_width
        self.threads = threads

        signature = {
            "source": Out(2 * sample_width),
            "sink_a": In(sample_width),
            "sink_b": In(sample_width)
        }
        for i in range(threads):
           signature[f"ready_{i}"] = Out(1)
           signature[f"valid_{i}"] = In(1)

        super().__init__(signature)

    def elaborate(self, platform):
        m = Module()

        input_a_ring = [Signal(self.sample_width, name=f"input_a_ring{i}") for i in range(self.threads - 1)]
        input_b_ring = [Signal(self.sample_width, name=f"input_b_ring{i}") for i in range(self.threads - 1)]
        for i in range(self.threads - 2):
            m.d.sync += [
                input_a_ring[i + 1].eq(input_a_ring[i]),
                input_b_ring[i + 1].eq(input_b_ring[i]),
            ]

        m.d.sync += input_a_ring[0].eq(self.sink_a)
        m.d.sync += input_b_ring[0].eq(self.sink_b)

        mult_node = Signal(2 * self.sample_width)
        mac_in_1 = Signal(self.sample_width)
        mac_in_2 = Signal(self.sample_width)

        m.d.comb += mult_node.eq(mac_in_1 * mac_in_2)
        m.d.comb += mac_in_1.eq(input_a_ring[-1])
        m.d.comb += mac_in_2.eq(input_b_ring[-1])
        m.d.comb += self.source.eq(mult_node)

        input_readys = Signal(self.threads, init=1)
        output_valids = Signal(self.threads, init=1)
        for i in range(self.threads):
            m.d.comb += self.__dict__[f"ready_{i}"].eq(input_readys.bit_select(i, 1))
            m.d.comb += self.__dict__[f"valid_{i}"].eq(output_valids.bit_select(i, 1))

        with m.If(input_readys == (1 << (self.threads - 1))):
            m.d.sync += input_readys.eq(1)
        with m.Else():
            m.d.sync += input_readys.eq(input_readys << 1)

        with m.If(output_valids == (1 << (self.threads - 1))):
            m.d.sync += output_valids.eq(1)
        with m.Else():
            m.d.sync += output_valids.eq(output_valids << 1)

        return m

def run_sim():
    thread_count = 3
    clk_freq = 60e6
    width = 16
    dut = TDMMultiply(width, thread_count)

    a = [i for i in range(100)]
    b = [i for i in range(100)]
    print("awa")
    async def tb(ctx):
        for i in range(100):
            ctx.set(dut.sink_a, a[i])
            ctx.set(dut.sink_b, b[i])
            await ctx.tick()

    sim = Simulator(dut)
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()


if __name__ == "__main__":
    run_sim()
