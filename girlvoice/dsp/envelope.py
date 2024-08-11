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


'''
An Envelope follower is essentially a special kind of low-pass filter
Its purpose is to trace the "envelope" of a signal. In a channel vocoder, this "envelope"
can be used to vary the amplification of one of the carrier signals.
'''
class EnvelopeFollower(wiring.Component):

    def __init__(self, sample_width=24, attack=0.75, decay=0.99):
        self.fraction_width = sample_width - 1
        self.attack_fp = C(int(attack * (2**(self.fraction_width))), signed(sample_width))
        self.attack_comp = C(int((1 - attack) * (2**(self.fraction_width))), signed(sample_width))

        self.decay_fp = C(int(decay * (2**(self.fraction_width))), signed(sample_width))
        self.decay_comp = C(int((1 - decay) * (2**(self.fraction_width))), signed(sample_width))
        print(bin(self.attack_fp.value))
        self.sample_width = sample_width
        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })

    def elaborate(self, platform):
        m = Module()

        mac_width = self.sample_width*2
        acc = Signal(signed(mac_width))

        x = Signal(signed(self.sample_width))
        y = Signal(signed(self.sample_width))

        param = Signal(signed(self.sample_width))
        param_comp = Signal(signed(self.sample_width))
        m.d.comb += param.eq(Mux(abs(x) > y, self.attack_fp, self.decay_fp))
        m.d.comb += param_comp.eq(Mux(abs(x) > y, self.attack_comp, self.decay_comp))

        m.d.comb += self.source.payload.eq(y)
        m.d.comb += x.eq(self.sink.payload)

        with m.FSM():
            with m.State("LOAD"):
                m.d.sync += self.source.valid.eq(0)
                m.d.comb += self.sink.ready.eq(1)
                with m.If(self.sink.valid):
                    m.d.sync += acc.eq(abs(x) * param_comp)
                    m.next = "MULT_Y"
            with m.State("MULT_Y"):
                m.d.sync += acc.eq(acc + (param * y))
                m.next = "READY"
            with m.State("READY"):
                m.d.sync += self.source.valid.eq(1)
                with m.If(self.source.ready):
                    m.d.sync += y.eq(acc >> self.fraction_width)
                    m.next = "LOAD"
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


def generate_ramp(freq, duration, fs, sample_width):
    num_samples = duration * fs
    t = np.linspace(0, duration, num_samples)
    input_samples = signal.sawtooth(2 * np.pi * freq * t) * t
    input_samples *= (2**(sample_width - 1))
    input_samples = np.flip(input_samples)
    input_samples[0:int(0.1*num_samples)] = 0
    return (t, input_samples)

def generate_chirp(duration, fs, start_freq, end_freq, sample_width):
    num_samples = duration * fs
    t = np.linspace(0, duration, num_samples)

    x = signal.chirp(t, f0 = start_freq, f1=end_freq, t1=duration)
    x = x * signal.windows.tukey(num_samples, 0.05)
    x *= 2**(sample_width-1)
    return (t, x)

def bode_plot(fs, duration, end_freq, input, output):
    fft_out = np.fft.fft(output)

    #freq = np.fft.fftfreq(n=end_freq, d=1/fs)
    freq = np.linspace(1, end_freq, fs*duration)
    fft_in = np.fft.fft(input)
    h = fft_out / fft_in

    half = math.floor(len(h)/2)
    resp = h[0:half]
    gain = 10 * np.log10(np.abs(resp))
    #phase = np.angle(h, deg=True)
    subplt = plt.subplot(122)
    subplt.plot(freq[0:half], gain, label="Gain")
    subplt.set_xscale("log")



def run_sim():
    clk_freq = 60e6
    bit_width = 32
    dut = EnvelopeFollower(sample_width=bit_width)

    duration = 1
    fs = 48000
    start_freq = 1
    end_freq = 23000
    test_sig_freq = 5000
    (t, input_samples) = generate_ramp(test_sig_freq, duration, fs, bit_width)
    # (t, input_samples) = generate_chirp(duration, fs, start_freq, end_freq, bit_width)

    # freq = np.linspace(1, end_freq, duration*fs)
    # fft_in = np.fft.fft(input_samples)
    # plt.plot(freq, np.abs(fft_in))
    # plt.show()
    output_samples = []
    async def tb(ctx):
        for sample in input_samples:
            await stream_put(ctx, dut.sink, int(sample))
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
        ax2.plot(t, input_samples, alpha=0.5, label="Input")
        ax2.plot(t, output_samples, alpha=0.5, label="Output")
        ax2.set_xlabel('time (s)')
        plt.title('Envelope Follower')
        plt.grid(True)
        # # plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
        plt.legend()
        # plt.savefig(f"{type(dut).__name__}.png")
        plt.show()




if __name__ == "__main__":
    run_sim()