#!/usr/bin/env python3
import os
import time
from tracemalloc import start
import numpy as np
from scipy.io import wavfile
import matplotlib.pyplot as plt

from amaranth import *
from amaranth.sim import Simulator
from girlvoice.dsp.envelope import EnvelopeFollower
from girlvoice.dsp.utils import generate_impulse
from girlvoice.stream import stream_get, stream_put

from girlvoice.dsp.tdm_slice import TDMMultiply
from girlvoice.dsp.bandpass_iir import BandpassIIR


def run_sim():
    clk_freq = 60e6
    bit_width = 18
    fs = 48000
    m = Module()
    m.submodules.mult = mult = TDMMultiply(sample_width=bit_width, num_threads=3)
    m.submodules.bandpass = bandpass = BandpassIIR(
        center_freq=1e3,
        passband_width=500,
        filter_order=1,
        sample_width=bit_width,
        fs=fs,
        mult_slice=mult,
    )
    m.submodules.env = envelope = EnvelopeFollower(
        bit_width, fs, attack_halflife=0.1, decay_halflife=25, mult_slice=mult
    )
    (t, input_samples) = generate_impulse(0.2, fs, bit_width)

    output_samples = []
    start_time = time.time()

    async def tb(ctx):
        samples_processed = 0
        for sample in input_samples:
            await stream_put(ctx, dut.sink, int(sample))
            output_samples.append(await stream_get(ctx, dut.source))
            await ctx.tick()
            samples_processed += 1
            if samples_processed % 1000 == 0:
                elapsed = time.time() - start_time
                print(
                    f"{samples_processed}/{len(t)} Samples processed in {elapsed} sec"
                )

    sim = Simulator(m)
    sim.add_clock(1 / clk_freq)
    sim.add_testbench(tb)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()
        # bode_plot(fs, duration, end_freq, input_samples, output_samples)

    wavfile.write("amen_bp.wav", rate=fs, data=np.array(output_samples, dtype=np.int32))
    plt.plot(t, input_samples, alpha=0.5, label="Input")
    plt.plot(t, output_samples, alpha=0.5, label="Output")
    plt.xlabel("time (s)")
    plt.title("Bandpass filter")
    plt.grid(True)
    # # plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
    plt.legend()
    # plt.savefig(f"{type(dut).__name__}.png")
    plt.show()


if __name__ == "__main__":
    run_sim()
