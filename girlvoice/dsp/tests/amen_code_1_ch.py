#!/usr/bin/env python3
import os
import numpy as np
from scipy.io import wavfile
import matplotlib.pyplot as plt

from amaranth import *
from amaranth.sim import Simulator
from girlvoice.stream import stream_get, stream_put

from girlvoice.dsp.tests.amen_envelope import import_wav
from girlvoice.dsp.vocoder import StaticVocoderChannel
from girlvoice.dsp.bandpass_iir import BandpassIIR

def run_sim():
    clk_freq = 60e6
    bit_width = 16
    fs = 44100
    dut = StaticVocoderChannel(channel_freq=150, channel_width=50, fs=fs, sample_width=bit_width)
    # dut = BandpassIIR(10e3, 20e3, filter_order=4, sample_width=bit_width, fs=fs)
    (t, input_samples) = import_wav('./amen_break_441khz_16bit.wav')

    input_samples = input_samples * .8

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
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        # bode_plot(fs, duration, end_freq, input_samples, output_samples)

    wavfile.write("amen_1_ch.wav", rate=fs, data=np.array(output_samples, dtype=np.int16))
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