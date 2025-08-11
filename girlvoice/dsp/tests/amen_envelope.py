#!/usr/bin/env python3
import os
import numpy as np
from scipy import signal
from scipy.io import wavfile
import matplotlib.pyplot as plt

from amaranth import *
from amaranth.sim import Simulator
from girlvoice.stream import stream_get, stream_put

from girlvoice.dsp.envelope import EnvelopeFollower


def import_wav(path, bit_shift=0):
    # Load the WAV file
    sample_rate, data = wavfile.read(path)
    n = data.shape[0]
    t = np.linspace(0, n / sample_rate, n)
    n = np.left_shift(n, bit_shift)
    # Print the sample rate and the shape of the data array
    print(f"Sample rate: {sample_rate}")
    print(f"Data shape: {data.shape}")
    print(f"Data type: {type(data[0][0])}")

    return (t, data[:, 0])


def hack_env(samples):
    b, a = signal.butter(1, 10, "lowpass", fs=48000)
    abs_samples = np.abs(samples)
    filtered = signal.lfilter(b, a, abs_samples)
    return filtered


def run_sim():
    clk_freq = 60e6
    bit_width = 16
    dut = EnvelopeFollower(
        sample_width=bit_width, attack_halflife=0.1, decay_halflife=25
    )

    fs = 48000
    (t, input_samples) = import_wav("./hotdog.wav")
    t = t[:fs]
    input_samples = input_samples[:fs]

    output_samples = []

    async def tb(ctx):
        samples_processed = 0
        for sample in input_samples:
            await stream_put(ctx, dut.sink, int(sample))
            output_samples.append(await stream_get(ctx, dut.source))
            await ctx.tick()
            samples_processed += 1
            if samples_processed % 10000 == 0:
                print(f"{samples_processed}/{len(t)} Samples processed")

    sim = Simulator(dut)
    sim.add_clock(1 / clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        # bode_plot(fs, duration, end_freq, input_samples, output_samples)
        test_samples = hack_env(input_samples)
        plt.plot(t, input_samples, alpha=0.5, label="Input")
        plt.plot(t, output_samples, alpha=0.5, label="Output")
        plt.plot(t, test_samples, label="Trying so hard")
        plt.xlabel("time (s)")
        plt.title("Envelope Follower")
        plt.grid(True)
        # # plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
        plt.legend()
        # plt.savefig(f"{type(dut).__name__}.png")
        plt.show()


if __name__ == "__main__":
    run_sim()
