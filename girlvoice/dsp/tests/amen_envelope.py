#!/usr/bin/env python3
import os
import numpy as np
from scipy.io import wavfile
import matplotlib.pyplot as plt

from amaranth import *
from amaranth.sim import Simulator
from girlvoice.dsp.envelope import EnvelopeFollower, stream_get, stream_put

def import_wav(path):
    # Load the WAV file
    sample_rate, data = wavfile.read(path)
    n = data.shape[0]
    t = np.linspace(0, n/sample_rate, n)
    # Print the sample rate and the shape of the data array
    print(f'Sample rate: {sample_rate}')
    print(f'Data shape: {data.shape}')
    print(f"Data type: {type(data[0][0])}")

    return (t, data[:, 0])

def run_sim():
    clk_freq = 60e6
    bit_width = 16
    dut = EnvelopeFollower(sample_width=bit_width, attack=0.75, decay=0.9999)

    fs = 44100
    (t, input_samples) = import_wav('./amen_break_441khz_16bit.wav')

    output_samples = []
    async def tb(ctx):
        samples_processed = 0
        for sample in input_samples:
            output_samples.append(await stream_get(ctx, dut.source))
            await stream_put(ctx, dut.sink, int(sample))
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
        sim.run()
        # bode_plot(fs, duration, end_freq, input_samples, output_samples)
        plt.plot(t, input_samples, alpha=0.5, label="Input")
        plt.plot(t, output_samples, alpha=0.5, label="Output")
        plt.xlabel('time (s)')
        plt.title('Envelope Follower')
        plt.grid(True)
        # # plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
        plt.legend()
        # plt.savefig(f"{type(dut).__name__}.png")
        plt.show()




if __name__ == "__main__":
    run_sim()