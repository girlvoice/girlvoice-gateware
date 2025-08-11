#!/usr/bin/env python3
import os
import random
from typing import List
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
            "sink_b": In(signed(sample_width)),
        }
        self.thread_ids = range(self.num_threads)
        for i in self.thread_ids:
            signature[f"sink_a_{i}"] = In(signed(sample_width))
            signature[f"sink_b_{i}"] = In(signed(sample_width))
            valid_init = 1 if i == 0 else 0
            signature[f"valid_{i}"] = Out(1, init=valid_init)

        self.utilized_threads = []
        super().__init__(signature)

    def _get_next_thread_id(self):
        next_tid = -1
        for tid in self.thread_ids:
            if tid not in self.utilized_threads:
                return tid
        return tid

    # Returns a new unique set of IO ports for a client module to use
    # Ensures that modules sharing the slice dont have to guess which ports of the interface to use
    def get_next_thread_ports(self) -> List[Signal]:
        tid = self._get_next_thread_id()
        if tid == -1:
            raise AttributeError("TDMMultiply has no threads remaining")
        self.utilized_threads.append(tid)
        sink_a = self.__dict__[f"sink_a_{tid}"]
        sink_b = self.__dict__[f"sink_b_{tid}"]
        valid = self.__dict__[f"valid_{tid}"]
        return sink_a, sink_b, valid

    def elaborate(self, platform):
        m = Module()

        # Sink input multiplexing
        self.sink_a = Signal(signed(self.sample_width))
        self.sink_b = Signal(signed(self.sample_width))

        sink_idx = Signal(range(self.num_threads), init=self.num_threads - 1)
        sink_a_mux = Array(
            [self.__dict__[f"sink_a_{i}"] for i in range(self.num_threads)]
        )
        sink_b_mux = Array(
            [self.__dict__[f"sink_b_{i}"] for i in range(self.num_threads)]
        )
        with m.If(sink_idx == self.num_threads - 1):
            m.d.sync += sink_idx.eq(0)
        with m.Else():
            m.d.sync += sink_idx.eq(sink_idx + 1)
        m.d.comb += self.sink_a.eq(sink_a_mux[sink_idx])
        m.d.comb += self.sink_b.eq(sink_b_mux[sink_idx])

        # Input delay registers
        input_a_ring = [
            Signal(self.sample_width, name=f"input_a_ring{i}")
            for i in range(self.num_threads - 1)
        ]
        input_b_ring = [
            Signal(self.sample_width, name=f"input_b_ring{i}")
            for i in range(self.num_threads - 1)
        ]
        m.d.sync += [
            input_a_ring[i + 1].eq(input_a_ring[i]) for i in range(self.num_threads - 2)
        ]
        m.d.sync += [
            input_b_ring[i + 1].eq(input_b_ring[i]) for i in range(self.num_threads - 2)
        ]

        m.d.sync += input_a_ring[0].eq(self.sink_a)
        m.d.sync += input_b_ring[0].eq(self.sink_b)

        # Multiplier slice I/O
        mult_out_node = Signal(signed(2 * self.sample_width))
        mult_in_node_a = Signal(signed(self.sample_width))
        mult_in_node_b = Signal(signed(self.sample_width))

        m.d.comb += mult_out_node.eq(mult_in_node_a * mult_in_node_b)
        m.d.comb += mult_in_node_a.eq(input_a_ring[-1])
        m.d.comb += mult_in_node_b.eq(input_b_ring[-1])
        m.d.comb += self.source.eq(mult_out_node)

        # Valid/Ready round robin
        for i in range(self.num_threads - 1):
            m.d.sync += self.__dict__[f"valid_{i + 1}"].eq(self.__dict__[f"valid_{i}"])

        m.d.sync += self.__dict__[f"valid_0"].eq(
            self.__dict__[f"valid_{self.num_threads - 1}"]
        )

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
    sim.add_clock(1 / clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()


if __name__ == "__main__":
    run_sim()
