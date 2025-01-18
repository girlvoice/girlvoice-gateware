#!/usr/bin/env python3
import os
import random
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream

from amaranth.sim import Simulator

class TDMMultiply(wiring.Component):
    def __init__(self, sample_width, num_threads):
        self.sample_width = sample_width
        self.num_threads = num_threads

        signature = {
            "source": Out(signed(2 * sample_width)),
            "sink_a": In(signed(sample_width)),
            "sink_b": In(signed(sample_width))
        }
        self.thread_ids = range(self.num_threads)
        for i in self.thread_ids:
           signature[f"ready_{i}"] = Out(1)
           signature[f"valid_{i}"] = In(1)

        self.utilized_threads = []
        super().__init__(signature)

    def _get_next_thread_id(self):
        next_tid = -1
        for tid in self.thread_ids:
            if tid not in self.utilized_threads:
                return tid
        return tid

    def get_next_thread_ports(self) -> Signal:
        tid = self._get_next_thread_id()
        if tid == -1:
            raise AttributeError("TDMMultiply has no threads remaining")
        self.utilized_threads.append(tid)
        return self.__dict__[f"ready_{tid}"], self.__dict__[f"valid_{tid}"]

    def elaborate(self, platform):
        m = Module()

        input_a_ring = [Signal(self.sample_width, name=f"input_a_ring{i}") for i in range(self.num_threads - 1)]
        input_b_ring = [Signal(self.sample_width, name=f"input_b_ring{i}") for i in range(self.num_threads - 1)]
        for i in range(self.num_threads - 2):
            m.d.sync += [
                input_a_ring[i + 1].eq(input_a_ring[i]),
                input_b_ring[i + 1].eq(input_b_ring[i]),
            ]

        m.d.sync += input_a_ring[0].eq(self.sink_a)
        m.d.sync += input_b_ring[0].eq(self.sink_b)

        mult_out_node = Signal(signed(2 * self.sample_width))
        mult_in_node_a = Signal(signed(self.sample_width))
        mult_in_node_b = Signal(signed(self.sample_width))

        m.d.comb += mult_out_node.eq(mult_in_node_a * mult_in_node_b)
        m.d.comb += mult_in_node_a.eq(input_a_ring[-1])
        m.d.comb += mult_in_node_b.eq(input_b_ring[-1])
        m.d.comb += self.source.eq(mult_out_node)

        input_readys = Signal(self.num_threads, init=1)
        output_valids = Signal(self.num_threads, init=1)
        for i in range(self.num_threads):
            m.d.comb += self.__dict__[f"ready_{i}"].eq(input_readys.bit_select(i, 1))
            m.d.comb += self.__dict__[f"valid_{i}"].eq(output_valids.bit_select(i, 1))

        with m.If(input_readys == (1 << (self.num_threads - 1))):
            m.d.sync += input_readys.eq(1)
        with m.Else():
            m.d.sync += input_readys.eq(input_readys << 1)

        with m.If(output_valids == (1 << (self.num_threads - 1))):
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
