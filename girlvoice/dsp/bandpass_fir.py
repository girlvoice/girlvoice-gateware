#!/usr/bin/env python3
import os
import math
from math import ceil, log2
import numpy as np
from matplotlib import pyplot as plt
from scipy import signal

from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream
from amaranth.sim import Simulator

from girlvoice.stream import stream_get, stream_put


def butter_bandpass(lowcut, highcut, fs, order=5):
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = signal.butter(order, [low, high], btype='band')
    return b, a


def butter_bandpass_filter(data, lowcut, highcut, fs, order=5):
    b, a = butter_bandpass(lowcut, highcut, fs, order=order)
    y = signal.lfilter(b, a, data)
    return y
class BandpassFIR(wiring.Component):

    def __init__(self, cutoff_freq, passband_width, filter_order=24, integer_width=16, fraction_width=16, samplerate=48e3):
        band_edges = [cutoff_freq - passband_width/2, cutoff_freq + passband_width / 2]

        print(f"Passband {band_edges[0]} - {band_edges[1]}")

        super().__init__({
            "sink": In(stream.Signature(signed(integer_width))),
            "source": Out(stream.Signature(signed(integer_width)))
        })

        taps = signal.firwin(filter_order+1, cutoff=band_edges, fs=samplerate, pass_zero=False, window='hamming')
        self.taps_raw = taps
        self.integer_width = integer_width
        self.fraction_width = fraction_width
        assert integer_width <= fraction_width, f"Bitwidth {integer_width} must not exceed {fraction_width}"
        self.taps = taps_fp = [int(x * 2**fraction_width) for x in taps]
        print(f"Filter taps before fixed point conversion: {taps}")
        print(f"Filter taps after fixed point conversion {taps_fp}")

        self.gamma = integer_width + integer_width + fraction_width + ceil(log2(sum([abs(x) for x in taps])))
        print(f"Required accumulator width: {self.gamma}")


    def elaborate(self, platform):
        m = Module()

        width = self.integer_width + self.fraction_width
        taps = Array([Const(x, signed(width)) for x in self.taps])

        ring_buf = Array([Signal(signed(width)) for _ in range(len(self.taps))])

        pipeline_dsp = True
        if pipeline_dsp:
            idx = Signal(range(len(self.taps)))
            acc = Signal(signed(width ))

            ring_buf_i = Signal(signed(width))
            taps_i = Signal(signed(width))
            m.d.comb += taps_i.eq(taps[idx])
            m.d.comb += ring_buf_i.eq(ring_buf[idx])


            """
            Incoming samples have fp representation of int_width.0 (all integer)
            Tap values have fp representation of int_width.frac_width
            """
            with m.FSM():
                with m.State("LOAD"):
                    m.d.comb += self.sink.ready.eq(1)
                    m.d.sync += self.source.valid.eq(0)
                    with m.If(self.sink.valid):
                        m.d.sync += [ring_buf[i + 1].eq(ring_buf[i]) for i in range(len(self.taps) - 1)]
                        m.d.sync += ring_buf[0].eq(self.sink.payload)
                        m.d.sync += idx.eq(0)
                        m.d.sync += acc.eq(0)
                        m.next = "CALC"
                with m.State("CALC"):
                    m.d.sync += idx.eq(idx + 1)
                    m.d.sync += acc.eq(acc + ((ring_buf_i * taps_i)))
                    with m.If(idx == len(self.taps) - 1):
                        m.d.sync += self.source.payload.eq(acc >> (len(acc) - self.integer_width))
                        m.d.sync += self.source.valid.eq(1)
                        m.next = "LOAD"
        else:
            with m.If(self.sink.valid):
                m.d.sync += [ring_buf[i + 1].eq(ring_buf[i]) for i in range(len(self.taps) - 1)]
                m.d.sync += ring_buf[0].eq(self.sink.payload)

            m.d.comb += self.source.valid.eq(self.sink.valid)

            y = sum((ring_buf[i] * taps[i]) >> self.fraction_width for i in range(len(self.taps)))
            m.d.comb += self.source.payload.eq(y)

        return m


# Testbench ----------------------------------------

def generate_chirp(duration, fs, start_freq, end_freq, sample_width):
    num_samples = duration * fs
    t = np.linspace(0, duration, num_samples)

    x = signal.chirp(t, f0 = start_freq, f1=end_freq, t1=duration)
    x = x * signal.windows.tukey(num_samples, 0.05)
    x *= 2**(sample_width-1)
    return (t, x)

def bode_plot(fs, duration, end_freq, input, output, taps):
    fft_out = np.fft.fft(output)

    freq = np.linspace(1, end_freq, fs*duration)
    fft_in = np.fft.fft(input)
    h = fft_out / fft_in

    half = math.floor(len(h)/2)
    resp = h[0:half]
    gain = 10 * np.log10(np.abs(resp))
    #phase = np.angle(h, deg=True)
    subplt = plt.subplot(122)
    # subplt.plot(freq[0:half], gain, label="Gain")
    # subplt.set_xscale("log")
    subplt.set_xlabel("Frequency log(Hz)")
    subplt.set_ylabel("Gain (dB)")

    w_ideal, h_ideal = signal.freqz(taps, 1, freq, fs=fs)
    subplt.plot(w_ideal, 10*np.log10(np.abs(h_ideal)))


def run_sim():
    clk_freq = 60e6
    sample_width = 16 # Number of 2s complement bits
    fs = 48000
    dut = BandpassFIR(cutoff_freq=10, passband_width=5, samplerate=fs, integer_width=sample_width, filter_order=128)

    duration = 5
    start_freq = 1
    end_freq = 23000
    test_sig_freq = 5000
    (t, input_samples) = generate_chirp(duration, fs, start_freq, end_freq, sample_width)

    output_samples = np.zeros(duration * fs)
    async def tb(ctx):
        samples_processed = 0
        for sample in input_samples:
            await stream_put(ctx, dut.sink, int(sample))
            output_samples[samples_processed] = (await stream_get(ctx, dut.source))
            await ctx.tick()
            samples_processed += 1
            if samples_processed % 10000 == 0:
                print(f"{samples_processed}/{len(t)} Samples processed")

    sim = Simulator(dut)
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        # sim.run()
        ax2 = plt.subplot(121)
        bode_plot(fs, duration, end_freq, input_samples, output_samples, dut.taps_raw)
        ax2.plot(t, input_samples, alpha=0.5, label="Input")
        ax2.plot(t, output_samples, alpha=0.5, label="Output")
        ax2.set_xlabel('Time (s)')
        ax2.set_ylabel("Amplitude")
        plt.title('Bandpass FIR')
        plt.grid(True)
        # plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
        plt.legend()
        plt.savefig(f"{type(dut).__name__}.png")
        plt.show()

if __name__ == "__main__":
    run_sim()