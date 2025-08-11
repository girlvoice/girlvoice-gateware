#!/usr/bin/env python3
import os
import math
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream
from girlvoice.dsp.sine_synth import ParallelSineSynth
from girlvoice.dsp.tdm_slice import TDMMultiply

"""
Combined Envelope follower and VGA. Saves a multiplication by combining the two components
"""


class EnvelopeVGA(wiring.Component):
    def __init__(
        self,
        sample_width=24,
        fs=48000,
        attack_halflife=10,
        decay_halflife=20,
        mult_slice: TDMMultiply = None,
        formal=False,
    ):
        self.sample_width = sample_width
        self.fraction_width = sample_width - 1
        self.formal = formal

        attack_hl_samples = fs * attack_halflife / 1000.0
        attack = math.exp(math.log(0.5) / attack_hl_samples)

        decay_hl_samples = fs * decay_halflife / 1000.0
        decay = math.exp(math.log(0.5) / decay_hl_samples)

        print(f"Envelope Decay parameter: {decay}")
        print(f"Envelope Attack parameter: {attack}")

        self.attack_fp = C(
            int(attack * (2 ** (self.fraction_width))), signed(sample_width)
        )
        self.attack_comp = C(
            int((1 - attack) * (2 ** (self.fraction_width))), signed(sample_width)
        )

        self.decay_fp = C(
            int(decay * (2 ** (self.fraction_width))), signed(sample_width)
        )
        self.decay_comp = C(
            int((1 - decay) * (2 ** (self.fraction_width))), signed(sample_width)
        )

        self.mult = mult_slice
        super().__init__(
            {
                "sink": In(stream.Signature(signed(sample_width))),
                "carrier": In(stream.Signature(signed(sample_width))),
                "source": Out(stream.Signature(signed(sample_width))),
            }
        )

    def elaborate(self, platform):
        m = Module()

        mac_width = self.sample_width * 2
        acc = Signal(signed(mac_width))
        acc_quant = Signal(signed(self.sample_width))
        x = Signal(signed(self.sample_width))
        y = Signal(signed(self.sample_width))

        param = Signal(signed(self.sample_width))
        param_comp = Signal(signed(self.sample_width))
        m.d.comb += param.eq(Mux(abs(x) > y, self.attack_fp, self.decay_fp))
        m.d.comb += param_comp.eq(Mux(abs(x) > y, self.attack_comp, self.decay_comp))

        m.d.comb += x.eq(self.sink.payload)

        if self.mult is None:
            product = Signal(signed(mac_width))
            mac_in_1 = Signal(signed(self.sample_width))
            mac_in_2 = Signal(signed(self.sample_width))
            m.d.comb += product.eq(mac_in_1 * mac_in_2)
            m.d.comb += acc_quant.eq(product >> (self.fraction_width))

            # Saturation logic:
            with m.If(acc_quant >= 0):
                m.d.comb += self.source.payload.eq(acc_quant)
            with m.Else():
                m.d.comb += self.source.payload.eq(2 ** (self.sample_width - 1) - 1)

            with m.FSM():
                with m.State("LOAD"):
                    # m.d.comb += self.source.valid.eq(0)
                    m.d.comb += self.sink.ready.eq(1)
                    with m.If(self.sink.valid):
                        m.d.sync += acc.eq(0)
                        m.d.sync += mac_in_1.eq(param_comp)
                        m.d.sync += mac_in_2.eq(abs(x))
                        m.next = "MULT_Y"

                with m.State("MULT_Y"):
                    m.d.sync += acc.eq(product)
                    m.d.sync += mac_in_1.eq(param)
                    m.d.sync += mac_in_2.eq(y)
                    m.next = "ACC_Y"

                with m.State("ACC_Y"):
                    m.d.sync += acc.eq(acc + product)
                    m.d.sync += self.carrier.ready.eq(1)
                    m.next = "MULT_CARRIER"

                # ACC reg now contains the output of the envelope follower
                with m.State("MULT_CARRIER"):
                    m.d.sync += mac_in_1.eq(acc_quant)
                    m.d.sync += y.eq(acc_quant)
                    with m.If(self.carrier.valid):
                        m.d.sync += mac_in_2.eq(self.carrier.payload)
                        m.d.sync += self.carrier.ready.eq(0)
                        m.d.sync += self.source.valid.eq(1)
                        m.next = "READY"

                with m.State("READY"):
                    with m.If(self.source.ready):
                        m.d.sync += self.source.valid.eq(0)
                        m.next = "LOAD"
        else:
            mac_in_1, mac_in_2, mult_valid = self.mult.get_next_thread_ports()
            product = self.mult.source
            m.d.comb += self.source.payload.eq(acc_quant)
            m.d.comb += acc_quant.eq(acc >> (self.fraction_width))

            with m.If(self.sink.valid & self.sink.ready):
                m.d.sync += mac_in_1.eq(param_comp)
                m.d.sync += mac_in_2.eq(abs(x))

            load_carrier = Signal()
            m.d.comb += load_carrier.eq(self.carrier.valid & self.carrier.ready)

            with m.If(load_carrier):
                m.d.sync += y.eq(acc_quant)

            with m.If(self.source.valid & self.source.ready):
                m.d.sync += self.source.valid.eq(0)

            with m.FSM():
                with m.State("LOAD"):
                    m.d.comb += self.sink.ready.eq(~self.source.valid & mult_valid)
                    with m.If(self.sink.valid & self.sink.ready):
                        m.d.sync += acc.eq(0)
                        m.next = "MULT_Y"

                with m.State("MULT_Y"):
                    if self.formal:
                        m.d.sync += Assert(self.source.valid == 0)
                    with m.If(mult_valid):
                        m.d.sync += acc.eq(product)
                        m.d.sync += mac_in_1.eq(param)
                        m.d.sync += mac_in_2.eq(y)
                        m.next = "ACC_Y"

                with m.State("ACC_Y"):
                    with m.If(mult_valid):
                        m.d.sync += acc.eq(acc + product)
                        m.next = "MULT_CARRIER"

                # ACC reg now contains the output of the envelope follower
                with m.State("MULT_CARRIER"):
                    if self.formal:
                        m.d.sync += Assert(acc_quant >= 0)
                    m.d.comb += self.carrier.ready.eq(mult_valid)
                    with m.If(self.carrier.valid & mult_valid):
                        m.d.sync += [
                            mac_in_1.eq(acc_quant),
                            mac_in_2.eq(self.carrier.payload),
                        ]
                        m.next = "WAIT_VGA"

                with m.State("WAIT_VGA"):
                    with m.If(mult_valid):
                        m.d.sync += acc.eq(product)
                        m.d.sync += self.source.valid.eq(1)
                        m.next = "LOAD"

        return m


def run_sim():
    import matplotlib.pyplot as plt
    from amaranth.sim import Simulator
    from girlvoice.dsp.utils import generate_ramp
    from girlvoice.stream import stream_get, stream_put

    clk_freq = 60e6
    bit_width = 16
    fs = 48000
    synth_freq = 1000
    m = Module()
    m.submodules.synth = synth = ParallelSineSynth(
        [1000], fs=fs, sample_width=bit_width
    )
    m.submodules.mult = mult = TDMMultiply(bit_width, num_threads=2)
    m.submodules.env_vga = dut = EnvelopeVGA(
        sample_width=bit_width, fs=fs, mult_slice=mult, formal=True
    )
    wiring.connect(m, dut.carrier, synth.source)

    duration = 0.25
    test_sig_freq = 5000
    (t, input_samples) = generate_ramp(test_sig_freq, duration, fs, bit_width)

    output_samples = []

    async def tb(ctx):
        samples_processed = 0
        for sample in input_samples:
            await stream_put(ctx, dut.sink, int(sample))
            output_samples.append(await stream_get(ctx, dut.source))
            await ctx.tick()
            if samples_processed % 1000 == 0:
                print(f"{samples_processed}/{len(t)} Samples processed")
            samples_processed += 1

    sim = Simulator(m)
    sim.add_clock(1 / clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        ax2 = plt.subplot(111)
        ax2.plot(t, input_samples, alpha=0.5, label="Input")
        ax2.plot(t, output_samples, alpha=0.5, label="Output")
        ax2.set_xlabel("time (s)")
        plt.title("Envelope Follower")
        plt.grid(True)
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", borderaxespad=0.0)
        plt.legend()
        # plt.savefig(f"{type(dut).__name__}.png")
        plt.show()


if __name__ == "__main__":
    run_sim()
