import numpy as np
import scipy.signal as signal

def generate_chirp(duration, fs, start_freq, end_freq, sample_width):
    num_samples = duration * fs
    t = np.linspace(0, duration, num_samples)

    x = signal.chirp(t, f0 = start_freq, f1=end_freq, t1=duration)
    x = x * signal.windows.tukey(num_samples, 0.05)
    x *= 2**(sample_width-1)
    return (t, x)
