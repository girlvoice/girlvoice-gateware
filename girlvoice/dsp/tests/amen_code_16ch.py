#!/usr/bin/env python3
import os
import time
from tracemalloc import start
import numpy as np
from scipy.io import wavfile
import matplotlib.pyplot as plt

from amaranth import *
from amaranth.sim import Simulator
from girlvoice.stream import stream_get, stream_put

from girlvoice.dsp.tests.amen_envelope import import_wav
from girlvoice.dsp.vocoder import StaticVocoder

def run_sim():
    clk_freq = 60e6
    bit_width = 16
    fs = 44100
    dut = StaticVocoder(start_freq=100, end_freq=10e3, num_channels=16, fs=fs, sample_width=bit_width)
    (t, input_samples) = import_wav('./amen_break_441khz_16bit.wav')
    input_samples = input_samples * 0.8
    output_samples = []
    start_time = time.time()
    async def tb(ctx):
        samples_processed = 0
        for sample in input_samples:
            await stream_put(ctx, dut.sink, int(sample))
            output_samples.append(await stream_get(ctx, dut.source))
            await ctx.tick()
            samples_processed += 1
            if samples_processed % 10000 == 0:
                elapsed = time.time() - start_time
                print(f"{samples_processed}/{len(t)} Samples processed in {elapsed} sec")

    sim = Simulator(dut)
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        # bode_plot(fs, duration, end_freq, input_samples, output_samples)

    wavfile.write("amen_16_ch.wav", rate=fs, data=np.array(output_samples, dtype=np.int16))
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