import math
import numpy as np
import scipy.signal as signal
import matplotlib.pyplot as plt


def generate_chirp(duration, fs, start_freq, end_freq, sample_width, amp=1.0):
    num_samples = int(duration * fs)
    t = np.linspace(0, duration, num_samples)

    x = amp * signal.chirp(t, f0=start_freq, f1=end_freq, t1=duration, phi=90)
    # x = x * signal.windows.tukey(num_samples, 0.05)
    x *= 2 ** (sample_width - 1)
    return (t, x)


def bode_plot(fs, duration, end_freq, input, output, taps, taps_quant, suffix = ""):
    fft_out = np.fft.fft(output)

    freq = np.linspace(1, end_freq, (int(fs * duration)) // 2)
    fft_in = np.fft.fft(input)
    h = fft_out / fft_in

    half = math.floor(len(h) / 2)
    resp = h[0:half]
    gain = 20 * np.log10(np.abs(resp))

    w_ideal, h_ideal = signal.freqz(b=taps[0], a=taps[1], worN=freq, fs=fs)
    w_q, h_q = signal.freqz(b=taps_quant[0], a=taps_quant[1], worN=freq, fs=fs)
    # phase = np.angle(h, deg=True)
    subplt = plt.subplot(122)
    subplt.plot(w_ideal, gain, label=f"Simulated Gain {suffix}")
    # subplt.set_xscale("log")
    subplt.set_xlabel("Frequency log(Hz)")
    subplt.set_ylabel("Gain (dB)")

    subplt.plot(w_ideal, 20 * np.log10(np.abs(h_ideal)), label=f"Ideal Gain {suffix}")
    subplt.plot(w_q, 20 * np.log10(np.abs(h_q)), label=f"Quantized Coeff Gain {suffix}")


def generate_sine(duration, fs, freq, sample_width, amp=1):
    num_samples = int(duration * fs)
    t = np.linspace(0, duration, num_samples)

    x = amp * np.sin(freq * t * (2 * np.pi))
    x *= 2 ** (sample_width - 1)
    return (t, x)


def generate_ramp(freq, duration, fs, sample_width):
    num_samples = int(duration * fs)
    t = np.linspace(0, duration, num_samples)
    input_samples = signal.sawtooth(2 * np.pi * freq * t) * t
    input_samples *= 2 ** (sample_width - 1)
    input_samples = np.flip(input_samples)
    input_samples[0 : int(0.1 * num_samples)] = 0
    return (t, input_samples)


def generate_impulse(duration, fs, sample_width, start_time=0):
    if start_time >= duration:
        raise ValueError(f"Impulse cannot start after end of waveform. Start time: {start_time}, Duration: {duration}")
    num_samples = int(duration * fs)
    start_sample = int(start_time * fs)
    t = np.linspace(0, duration, num_samples)

    impulse = np.zeros(num_samples)
    impulse[start_sample:start_sample + 50] = 2 ** (sample_width - 1) - 1

    return (t, impulse)
