#!/usr/bin/env python3
import os
from amaranth import *
from amaranth.build import Platform
from amaranth.lib import wiring, stream
from amaranth.lib.wiring import Out, In
from amaranth.lib.fifo import AsyncFIFO
from amaranth.lib import data

from amaranth.sim import Simulator, Tick

class Signature(wiring.Signature):
    def __init__(self):
        members = {
            "lrclk": Out(1),
            "sdout": Out(1)
        }
        super().__init__(members)

class StereoPayload(data.StructLayout):
    def __init__(self, sample_width):
        super().__init__(
            {
                "left": signed(sample_width),
                "right": signed(sample_width)
            }
        )
    def __call__(self, value):
        return StereoView(self, value)

class StereoView(data.View):
    pass


class i2s_tx(wiring.Component):
    def __init__(self, sample_width=32, sink_domain="sync", phy_domain="sync"):
        self.sample_width = sample_width
        self._domain = phy_domain
        self._sink_domain = sink_domain
        super().__init__(
            {
                "sink": In(stream.Signature(StereoPayload(sample_width))),
                "sdout": Out(1),
                "lrclk": In(1),
                "sclk_falling": In(1)
            }
        )

    def elaborate(self, platform) -> Module:
        m = Module()

        phy_domain = self._domain
        input_stream = stream.Signature(StereoPayload(self.sample_width)).flip().create()
        if self._sink_domain != self._domain:
            m.submodules.cdc_fifo = self.cdc_fifo = AsyncFIFO(
                width=self.sample_width*2,
                depth=2,
                r_domain=self._domain,
                w_domain=self._sink_domain
            )

            wiring.connect(m, self.cdc_fifo.w_stream, wiring.flipped(self.sink))
            wiring.connect(m, input_stream, self.cdc_fifo.r_stream)
        else:
            wiring.connect(m, wiring.flipped(self.sink), input_stream)


        bit_count = Signal(range(32))
        shift_out = Signal(self.sample_width)
        shift_next = Signal(self.sample_width)

        with m.If(self.sclk_falling):
            m.d[phy_domain] += bit_count.eq(bit_count + 1)
            m.d[phy_domain] += shift_out.eq(shift_out << 1)

        with m.FSM(domain=phy_domain):
            with m.State("IDLE"):
                m.d[phy_domain] += self.sdout.eq(0)
                with m.If(~self.lrclk):
                    with m.If(bit_count == 0):
                        m.d.comb += input_stream.ready.eq(1)
                    with m.If(input_stream.valid & input_stream.ready):
                        m.d[phy_domain] += shift_out.eq(input_stream.p.left)
                        m.d[phy_domain] += shift_next.eq(input_stream.p.right)
                        m.next = "WRITE"
                with m.Else():
                    m.d[phy_domain] += shift_out.eq(shift_next)
                    m.next = "WRITE"

            with m.State("WRITE"):
                with m.If(self.sclk_falling):
                    m.d[phy_domain] += self.sdout.eq(shift_out[self.sample_width - 1])

                with m.If(bit_count >= (self.sample_width)):
                    with m.If(self.sclk_falling):
                        m.next = "IDLE"

        return m


class i2s_rx(wiring.Component):
    def __init__(self, sample_width=18, source_domain="sync", phy_domain="sync"):
        self.sample_width = sample_width
        self._domain = phy_domain
        self._source_domain = source_domain
        super().__init__(
            {
                "source": Out(stream.Signature(StereoPayload(sample_width))),
                "sdin": In(1),
                "lrclk": In(1),
                "sclk_falling": In(1),
            }
        )

    def elaborate(self, platform) -> Module:
        m = Module()

        phy_domain = self._domain
        output_stream = stream.Signature(StereoPayload(self.sample_width)).create()

        if self._source_domain != self._domain:
            m.submodules.cdc_fifo = self.cdc_fifo = AsyncFIFO(
                width=self.sample_width*2,
                depth=2,
                r_domain=self._source_domain,
                w_domain=self._domain
            )

            wiring.connect(m, self.cdc_fifo.w_stream, output_stream)
            wiring.connect(m, wiring.flipped(self.source), self.cdc_fifo.r_stream)
        else:
            wiring.connect(m, wiring.flipped(self.source), output_stream)


        shift_reg = Signal(32)
        bit_count = Signal(range(32))

        with m.If(self.sclk_falling):
            m.d[phy_domain] += bit_count.eq(bit_count + 1)


        with m.FSM(domain=phy_domain):
            with m.State("IDLE"):
                with m.If(self.sclk_falling):
                    m.d[phy_domain] += shift_reg.eq(0)
                with m.If(bit_count == 0):
                    m.next = "READ"
            with m.State("READ"):
                with m.If(self.sclk_falling):
                    m.d[phy_domain] += shift_reg.eq(Cat(self.sdin, shift_reg[:-1]))

                with m.If(bit_count >= self.sample_width):
                    with m.If(self.lrclk):
                        m.d[phy_domain] += output_stream.p.right.eq(shift_reg)
                        m.d[phy_domain] += output_stream.valid.eq(1)
                    with m.Else():
                        m.d[phy_domain] += output_stream.p.left.eq(shift_reg)
                    m.next = "IDLE"

        with m.If(output_stream.valid & output_stream.ready):
            m.d[phy_domain] += output_stream.valid.eq(0)

        return m

class I2SClockGenerator(wiring.Component):
    def __init__(self, domain: str, mclk_freq: float, sclk_freq: float, max_sample_width: int):
        assert max_sample_width in [32, 64]

        self.mclk_freq = mclk_freq
        self.sclk_freq = sclk_freq
        self.clk_ratio = int(mclk_freq // sclk_freq)
        self._domain = domain
        print(f"I2S clock divider: {self.clk_ratio}")
        self.sample_width = max_sample_width


        super().__init__({
            "sclk": Out(1),
            "lrclk": Out(1),
            "sclk_falling": Out(1),
        })

    def elaborate(self, platform):
        m = Module()
        clk_div = Signal(range(self.clk_ratio))
        bit_count = Signal(range(self.sample_width))

        sclk_negedge = Signal()
        sclk_last = Signal()

        m.d.comb += sclk_negedge.eq(~self.sclk & sclk_last)
        m.d.comb += self.sclk_falling.eq(sclk_negedge)
        m.d.sync += sclk_last.eq(self.sclk)

        with m.If(self.sclk_falling):
            m.d.sync += bit_count.eq(bit_count + 1)

        # with m.If(bit_count == (self.sample_width - 1)):
        #     with m.If(sclk_negedge):
        #         m.d.sync += self.lrclk.eq(~self.lrclk)

        # m.d.comb += self.sclk.eq(clk_div[-1])
        with m.If(clk_div >= (self.clk_ratio - 1)):
            m.d.sync += clk_div.eq(0)
            m.d.sync += self.sclk.eq(~self.sclk)
            with m.If(self.sclk & (bit_count == (self.sample_width - 1))):
                m.d.sync += self.lrclk.eq(~self.lrclk)
        with m.Else():
            m.d.sync += clk_div.eq(clk_div + 1)

        if self._domain != "sync":
            m = DomainRenamer({"sync": self._domain})(m)
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

class I2SController(wiring.Component):
    def __init__(self, sample_width, sys_clk_freq, sclk_freq, controller_domain = "sync", phy_domain = "sync"):
        self.rx = i2s_rx(sample_width, controller_domain, phy_domain)
        self.tx = i2s_tx(sample_width, controller_domain, phy_domain)

        if sample_width <= 32:
            max_sample_width = 32
        elif sample_width > 32 and sample_width <= 64:
            max_sample_width = 64
        else:
            raise ValueError(f"Sample width: {sample_width} exceeds maximum allowed")
        self.clocking = I2SClockGenerator(domain=phy_domain, mclk_freq=sys_clk_freq, sclk_freq=sclk_freq, max_sample_width=max_sample_width)

        super().__init__(
            {
                "sink": In(stream.Signature(StereoPayload(sample_width))),
                "source": Out(stream.Signature(StereoPayload(sample_width))),
                "sclk": Out(1),
                "lrclk": Out(1),
                "sdin": In(1),
                "sdout": Out(1)
            }
        )

    def elaborate(self, platform):
        m = Module()

        m.submodules.rx = self.rx
        m.submodules.tx = self.tx
        m.submodules.clocking = self.clocking

        m.d.comb += [
            self.rx.sclk_falling.eq(self.clocking.sclk_falling),
            self.tx.sclk_falling.eq(self.clocking.sclk_falling),
            self.rx.lrclk.eq(self.clocking.lrclk),
            self.tx.lrclk.eq(self.clocking.lrclk),
            self.rx.sdin.eq(self.sdin),
            self.sdout.eq(self.tx.sdout),
            self.lrclk.eq(self.clocking.lrclk),
            self.sclk.eq(self.clocking.sclk),
        ]

        wiring.connect(m, self.rx.source, wiring.flipped(self.source))
        wiring.connect(m, self.tx.sink, wiring.flipped(self.sink))

        return m


def tx_tb():
    sys_clk_freq = 60e6
    aud_clk_freq = 24.576e6
    sclk_freq = 64 * 48e3
    sample_width = 24
    m = Module()
    m.submodules.clk_gen = clk_gen = I2SClockGenerator(domain="mclk", mclk_freq=aud_clk_freq, sclk_freq=sclk_freq, max_sample_width=32)
    m.submodules.i2s_tx = dut = i2s_tx(sample_width=sample_width, sink_domain="sync", phy_domain="mclk")
    m.d.comb += [
        dut.lrclk.eq(clk_gen.lrclk),
        dut.sclk_falling.eq(clk_gen.sclk_falling)
    ]
    sim = Simulator(m)

    samples = [(C(i << 14, sample_width)) for i in range(32)]

    def process():
        yield dut.sink.valid.eq(0)
        yield Tick()
        while (yield ~dut.sink.ready):
            yield Tick()
            yield Tick("mclk")

        for i in range(len(samples)):
            yield dut.sink.p.left.eq(samples[i])
            yield dut.sink.valid.eq(1)
            yield Tick()
            if (yield dut.sink.ready):
                yield dut.sink.valid.eq(0)
            while (yield ~dut.sink.ready):
                yield Tick("mclk")
                # yield Tick()

    sim.add_process(process)
    sim.add_clock(1 / sys_clk_freq)
    sim.add_clock(1 / aud_clk_freq, domain="mclk")

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()


def rx_tb():
    sys_clk_freq = 64e6
    sclk_freq = 4e6
    m = Module()
    m.submodules.clk_gen = clk_gen = I2SClockGenerator(mclk_freq=sys_clk_freq, sclk_freq=sclk_freq, max_sample_width=32)
    m.submodules.i2s_rx = dut = i2s_rx(sample_width=16)
    m.d.comb += [
        dut.lrclk.eq(clk_gen.lrclk),
        dut.sclk_falling.eq(clk_gen.sclk_falling)
    ]
    sim = Simulator(m)

    samples_int = [i << 11 for i in range(32)]
    samples = [(C(i , 16)) for i in samples_int]

    print(len(samples_int))
    def process():
        j = 0
        for word in samples:
            sample_in = samples_int[j]
            for i in range(32):
                while (yield ~(clk_gen.sclk)):
                    yield Tick()

                if i < 16:
                    yield dut.sdin.eq(word[15 - i])
                else:
                    yield dut.sdin.eq(0)

                while (yield (clk_gen.sclk)):
                    yield Tick()

                if (yield dut.source.valid):
                    yield dut.source.ready.eq(1)
                    sample_out = yield dut.source.payload
                    yield Tick()
                    yield dut.source.ready.eq(0)
            assert sample_in == sample_out, f"Expected {sample_in}, got: {sample_out}"
            j += 1

    sim.add_process(process)
    sim.add_clock(1 / sys_clk_freq)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()


def controller_tb():
    sys_clk_freq = 24.576e6
    sclk_freq = 64 * 48e3
    m = Module()
    sample_width = 24
    m.submodules.i2s = dut = I2SController(
        sys_clk_freq=sys_clk_freq,
        sclk_freq=sclk_freq,
        sample_width=sample_width
    )
    wiring.connect(m, dut.sink, dut.source)
    sim = Simulator(m)


    samples_int = [i << 11 for i in range(32)]
    samples = [(C(i , sample_width)) for i in samples_int]

    print(len(samples_int))
    def process():
        j = 0
        for word in samples:
            sample_in = samples_int[j]
            for i in range(32):
                while (yield ~(dut.sclk)):
                    yield Tick()

                if i < sample_width:
                    yield dut.sdin.eq(word[(sample_width - 1) - i])
                else:
                    yield dut.sdin.eq(0)

                while (yield (dut.sclk)):
                    yield Tick()

                # if (yield dut.source.valid):
                #     yield dut.source.ready.eq(1)
                #     sample_out = yield dut.source.payload
                #     yield Tick()
                #     yield dut.source.ready.eq(0)
            # assert sample_in == sample_out, f"Expected {sample_in}, got: {sample_out}"
            j += 1


    sim.add_process(process)
    sim.add_clock(1 / sys_clk_freq)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()


def main():
    # controller_tb()
    tx_tb()
    # rx_tb()


if __name__ == "__main__":
    main()
