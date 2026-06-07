#!/usr/bin/env python3
import os
from amaranth import *
from amaranth.build import Platform
from amaranth.lib import wiring, stream
from amaranth.lib.wiring import Out, In
from amaranth.lib.fifo import AsyncFIFO

from amaranth.sim import Simulator, Tick

class Signature(wiring.Signature):
    def __init__(self):
        members = {
            "lrclk": Out(1),
            "sdout": Out(1)
        }
        super().__init__(members)

class i2s_tx(wiring.Component):
    def __init__(self, sys_clk_freq, sclk_freq, sample_width=32, sink_domain="sync", phy_domain="sync"):
        self.clk_ratio = int(sys_clk_freq // sclk_freq)
        self.sample_width = sample_width
        self.clk_div = Signal(range(self.clk_ratio))
        self._domain = phy_domain
        self._sink_domain = sink_domain
        super().__init__(
            {
                "sink": In(stream.Signature(sample_width)),
                "lrclk": Out(1),
                "sclk": Out(1),
                "sdout": Out(1),
            }
        )

    def elaborate(self, platform):
        m = Module()

        clk_div = self.clk_div

        input_stream = stream.Signature(self.sample_width).flip().create()
        if self._sink_domain != self.phy_domain:
            m.submodules.cdc_fifo = self.cdc_fifo = AsyncFIFO(
                width=self.sample_width,
                depth=4,
                r_domain=self._domain,
                w_domain=self._sink_domain
            )

            wiring.connect(m, self.cdc_fifo.w_stream, self.sink)
            wiring.connect(m, input_stream, self.cdc_fifo.r_stream)
        else:
            wiring.connect(m, self.sink, input_stream)

        sclk_last = Signal()
        sclk_negedge = Signal()

        m.d.comb += self.sclk.eq(clk_div[-1])
        with m.If(clk_div >= (self.clk_ratio - 1)):
            m.d.sync += clk_div.eq(0)
        with m.Else():
            m.d.sync += clk_div.eq(clk_div + 1)

        m.d.comb += sclk_negedge.eq(~self.sclk & sclk_last)
        m.d.sync += sclk_last.eq(self.sclk)

        bit_count = Signal(range(32))
        shift_out = Signal(self.sample_width)

        with m.If(sclk_negedge):
            m.d.sync += bit_count.eq(bit_count + 1)
            m.d.sync += shift_out.eq(shift_out << 1)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self.sdout.eq(0)
                with m.If(bit_count == 0):
                    m.d.comb += input_stream.ready.eq(1)
                with m.If(input_stream.valid & input_stream.ready):
                    m.d.sync += shift_out.eq(input_stream.payload)
                    m.next = "WRITE"
            with m.State("WRITE"):
                with m.If(sclk_negedge):
                    m.d.sync += self.sdout.eq(shift_out[self.sample_width - 1])

                with m.If(bit_count >= (self.sample_width)):
                    with m.If(sclk_negedge):
                        m.next = "IDLE"

        with m.If(bit_count == 31):
            with m.If(sclk_negedge):
                m.d.sync += self.lrclk.eq(~self.lrclk)

        if self._domain != "sync":
            m = DomainRenamer({"sync": self._domain})(m)


class i2s_rx(wiring.Component):
    def __init__(self, sys_clk_freq, sclk_freq, sample_width=18, source_domain="sync", phy_domain="sync"):
        self.clk_ratio = int(sys_clk_freq // sclk_freq)
        self.sample_width = sample_width
        self._domain = phy_domain
        self._source_domain = source_domain
        super().__init__(
            {
                "source": Out(stream.Signature(sample_width)),
                "lrclk": Out(1),
                "sclk": Out(1),
                "sdin": In(1),
            }
        )

    def elaborate(self, platform):
        m = Module()

        sclk_last = Signal()
        sclk_negedge = Signal()

        clk_div = Signal(range(self.clk_ratio))
        output_stream = stream.Signature(self.sample_width).create()

        if self._source_domain != self.phy_domain:
            m.submodules.cdc_fifo = self.cdc_fifo = AsyncFIFO(
                width=self.sample_width,
                depth=4,
                r_domain=self._source_domain,
                w_domain=self._domain
            )

            wiring.connect(m, self.cdc_fifo.w_stream, output_stream)
            wiring.connect(m, self.source, self.cdc_fifo.r_stream)
        else:
            wiring.connect(m, self.source, output_stream)

        m.d.comb += sclk_negedge.eq(~self.sclk & sclk_last)
        m.d.sync += sclk_last.eq(self.sclk)

        m.d.comb += self.sclk.eq(clk_div[-1])
        with m.If(clk_div >= (self.clk_ratio - 1)):
            m.d.sync += clk_div.eq(0)
        with m.Else():
            m.d.sync += clk_div.eq(clk_div + 1)

        shift_reg = Signal(32)
        bit_count = Signal(range(32))

        with m.If(sclk_negedge):
            m.d.sync += bit_count.eq(bit_count + 1)

        with m.If((bit_count == 31)):
            with m.If(sclk_negedge):
                m.d.sync += self.lrclk.eq(~self.lrclk)

        with m.FSM():
            with m.State("IDLE"):
                with m.If(sclk_negedge):
                    m.d.sync += shift_reg.eq(0)
                with m.If(bit_count == 0):
                    m.next = "READ"
            with m.State("READ"):
                with m.If(sclk_negedge):
                    m.d.sync += shift_reg.eq(Cat(self.sdin, shift_reg[:-1]))

                with m.If(bit_count >= self.sample_width):
                    m.d.sync += output_stream.payload.eq(shift_reg)
                    m.d.sync += output_stream.valid.eq(1)
                    m.next = "IDLE"

        with m.If(output_stream.valid & output_stream.ready):
            m.d.sync += output_stream.valid.eq(0)

        if self._domain != "sync":
            m = DomainRenamer({"sync": self._domain})(m)

class I2SClockGenerator(wiring.Component):
    def __init__(self, mclk_freq: float, sclk_freq: float):
        self.mclk_freq = mclk_freq
        self.sclk_freq = sclk_freq
        self.clk_ratio = int(mclk_freq // sclk_freq)
        super.__init__({
            "sclk": Out(1),
        })

    def elaborate(self, platform):
        m = Module()
        clk_div = Signal(range(self.clk_ratio))

        m.d.comb += self.sclk.eq(clk_div[-1])
        with m.If(clk_div >= (self.clk_ratio - 1)):
            m.d.sync += clk_div.eq(0)
        with m.Else():
            m.d.sync += clk_div.eq(clk_div + 1)

        return m

class I2STargetTx(wiring.Component):
    """
    A I2S target transmit interface. Clocks out samples in accordance with an external
    controller's serial clock.
    """

    def __init__(self, mclk_name: str,  mclk_freq: float, sample_width: int):
        self.sample_width = sample_width
        self.mclk_name = mclk_name
        super().__init__({
            "sink": In(stream.Signature(sample_width)),
            "sdout": Out(1),
            "lrclk": In(1),
            "sclk": In(1),
        })

    def elaborate(self, platform: Platform):
        m = Module()

        # Sink for incoming data to send over serial
        sink = self.sink

        sclk_last = Signal()
        sclk_negedge = Signal()

        lrclk_last = Signal()
        lrclk_edge = Signal()
        m.d.comb += lrclk_edge.eq(lrclk_last != self.lrclk)
        m.d.sync += lrclk_last.eq(self.lrclk)

        m.d.comb += sclk_negedge.eq(~self.sclk & sclk_last)
        m.d.sync += sclk_last.eq(self.sclk)

        bit_count = Signal(range(32))
        shift_out = Signal(self.sample_width)

        with m.If(sclk_negedge):
            m.d.sync += bit_count.eq(bit_count + 1)
            m.d.sync += shift_out.eq(shift_out << 1)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self.sdout.eq(0)
                with m.If(bit_count == 0):
                    m.d.comb += sink.ready.eq(1)
                with m.If(sink.valid & sink.ready):
                    m.d.sync += shift_out.eq(sink.payload)
                    m.next = "WRITE"
            with m.State("WRITE"):
                with m.If(sclk_negedge):
                    m.d.sync += self.sdout.eq(shift_out[self.sample_width - 1])

                with m.If(bit_count >= (self.sample_width) | lrclk_edge):
                    with m.If(sclk_negedge):
                        m.next = "IDLE"

        return m

class I2SPeripheralRx(wiring.Component):
    """
    A peripheral I2S recieve interface. Clocks in samples in accordance with an external
    serial clock. Produces its own sample clock. Frames data inside 32-bit wide sample windows
    """

    def __init__(self, mclk_name: str,  mclk_freq: float, sample_width: int):
        self.sample_width = sample_width
        self.mclk_name = mclk_name
        super().__init__({
            "sink": In(stream.Signature(sample_width)),
            "i2s": Out(Signature()),
            "sclk": In(1),
        })

    def elaborate(self, platform: Platform):
        m = Module()

        # Sink for incoming data to send over serial
        sink = self.sink

        sclk_last = Signal()
        sclk_negedge = Signal()

        m.d.comb += sclk_negedge.eq(~self.sclk & sclk_last)
        m.d.sync += sclk_last.eq(self.sclk)

        bit_count = Signal(range(32))
        shift_out = Signal(self.sample_width)

        with m.If(sclk_negedge):
            m.d.sync += bit_count.eq(bit_count + 1)
            m.d.sync += shift_out.eq(shift_out << 1)

        with m.FSM():
            with m.State("IDLE"):
                m.d.sync += self.i2s.sdout.eq(0)
                with m.If(bit_count == 0):
                    m.d.comb += sink.ready.eq(1)
                with m.If(sink.valid & sink.ready):
                    m.d.sync += shift_out.eq(sink.payload)
                    m.next = "WRITE"
            with m.State("WRITE"):
                with m.If(sclk_negedge):
                    m.d.sync += self.i2s.sdout.eq(shift_out[self.sample_width - 1])

                with m.If(bit_count >= (self.sample_width)):
                    with m.If(sclk_negedge):
                        m.next = "IDLE"

        with m.If(bit_count == 31 & sclk_negedge):
            m.d.sync += self.i2s.lrclk.eq(~self.i2s.lrclk)

        return m

class i2s(wiring.Component):
    source: Out(stream.Signature(32))
    sink: In(stream.Signature(32))

    sclk: Out(1)

    def __init__(self, sys_clk_freq, sclk_freq, sample_width=32):
        self.clk_ratio = int(sys_clk_freq // sclk_freq)
        self.rx = i2s_rx(
            sys_clk_freq=sys_clk_freq, sclk_freq=sclk_freq, sample_width=sample_width
        )
        self.tx = i2s_tx(
            sys_clk_freq=sys_clk_freq, sclk_freq=sclk_freq, sample_width=sample_width
        )
        super().__init__()

    def elaborate(self, platform):
        m = Module()

        m.submodules.rx = rx = self.rx
        m.submodules.tx = tx = self.tx

        clk_div = Signal(range(self.clk_ratio))

        m.d.comb += [
            tx.sclk.eq(self.sclk),
            rx.sclk.eq(self.sclk),
        ]

        with m.If(clk_div >= (self.clk_ratio - 1) // 2):
            m.d.sync += clk_div.eq(0)
            m.d.sync += self.sclk.eq(~self.sclk)
        with m.Else():
            m.d.sync += clk_div.eq(clk_div + 1)

        wiring.connect(m, wiring.flipped(self.source), rx.source)
        wiring.connect(m, wiring.flipped(self.sink), tx.sink)

        return m


def tx_tb():
    sys_clk_freq = 64e6
    sclk_freq = 4e6
    dut = i2s_tx(sys_clk_freq=sys_clk_freq, sclk_freq=sclk_freq, sample_width=18)
    sim = Simulator(dut)

    samples = [(C(i, 32)) for i in range(32)]

    def process():
        while (yield ~dut.sink.ready):
            yield Tick()

        for i in range(len(samples)):
            yield dut.sink.payload.eq(samples[i])
            yield dut.sink.valid.eq(1)
            yield Tick()
            # yield dut.sink.valid.eq(0)
            while (yield ~dut.sink.ready):
                yield Tick()

    sim.add_process(process)
    sim.add_clock(1 / sys_clk_freq)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()


def rx_tb():
    sys_clk_freq = 64e6
    sclk_freq = 4e6
    dut = i2s_rx(sys_clk_freq=sys_clk_freq, sclk_freq=sclk_freq)
    sim = Simulator(dut)

    samples = [(C(i << 14, 32)) for i in range(32)]

    def process():
        sample_in = 0
        for word in samples:
            for i in range(32):
                while (yield ~(dut.sclk)):
                    yield Tick()
                yield dut.sdin.eq(word[31 - i])

                while (yield (dut.sclk)):
                    yield Tick()
                if (yield dut.source.valid):
                    yield dut.source.ready.eq(1)
                    sample_out = yield dut.source.data
                    yield Tick()
                    yield dut.source.ready.eq(0)
            assert sample_in == sample_out, f"Expected {sample_in}, got: {sample_out}"
            sample_in += 1

    sim.add_process(process)
    sim.add_clock(1 / sys_clk_freq)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()


def main():
    tx_tb()
    rx_tb()


if __name__ == "__main__":
    main()
