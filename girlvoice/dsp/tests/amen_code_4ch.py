#!/usr/bin/env python3
import os
import time
import numpy as np
from scipy.io import wavfile
import matplotlib.pyplot as plt

from amaranth import *
from amaranth.sim import Simulator
from girlvoice.stream import stream_get, stream_put, new_observer

from girlvoice.dsp.tests.amen_envelope import import_wav
from girlvoice.dsp.vocoder import StaticVocoder



def run_sim():
    clk_freq = 60e6
    bit_width = 16
    fs = 44100
    num_channels = 4
    dut = StaticVocoder(start_freq=100, end_freq=2e3, num_channels=num_channels, fs=fs, sample_width=bit_width)
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

    env_ch = []
    bp_ch = []
    output_ch = []
    for ch in dut.channels:
        next_env = []
        next_bp = []
        next_output = []
        sim.add_testbench(new_observer(ch.envelope.source, next_env), background=True)
        sim.add_testbench(new_observer(ch.bandpass.source, next_bp), background=True)
        sim.add_testbench(new_observer(ch.source, next_output), background=True)
        env_ch.append(next_env)
        bp_ch.append(next_bp)
        output_ch.append(output_ch)

    os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}"
    with sim.write_vcd(dutname + f".vcd"):
        sim.run()

    wavfile.write("amen_4_ch.wav", rate=fs, data=np.array(output_samples, dtype=np.int16))
    rows = 2
    cols = 2
    fig, axs = plt.subplots(rows, cols)
    axs[1].plot(t, input_samples, alpha=0.5, label="Input")
    axs[1].plot(t, output_samples, alpha=0.5, label="Output")

    for ch_num in range(num_channels):
        axn = plt.subplot(rows, cols, ch_num + 1)
        # axn.title(f"Channel {ch_num}")
        axn.plot(t, env_ch[ch_num], alpha=0.5, label=f"Envelope {ch_num} Output")
        axn.plot(t, bp_ch[ch_num], alpha=0.5, label=f"Bandpass {ch_num} Output")
        axn.plot(t, output_ch[ch_num], alpha=0.5, label=f"Channel {ch_num} Output")

    plt.xlabel('time (s)')
    plt.title('4 Channel vocoder')
    plt.grid(True)
    plt.legend()
    # plt.savefig(f"{type(dut).__name__}.png")
    plt.show()




if __name__ == "__main__":
    run_sim()