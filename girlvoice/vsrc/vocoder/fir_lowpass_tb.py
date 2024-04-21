from scipy import signal
import numpy as np
import matplotlib.pyplot as plt
import cocotb
from cocotb.triggers import RisingEdge
from cocotb.clock import Clock


@cocotb.test()
def lp_fir(dut):
    clk = dut.clk
    sample_in = dut.sample_in
    sample_out = dut.sample_out
    reset = dut.reset

    duration = 1
    fs = 44100
    freq = 1
    end_freq = 10000
    sample_in.value = 0
    reset.value = 0
    clk.value = 0

    cocotb.fork(Clock(dut.clk,5000).start())

    yield RisingEdge(clk)


    samples = duration * fs
    t = np.linspace(0, duration, samples, endpoint = True)
    samples_out = np.arange(samples, dtype=np.int16)

    samples_in = signal.chirp(t,  freq, duration, end_freq) * 32767

    dut.reset = 1
    yield RisingEdge(clk)
    dut.reset = 0
    yield RisingEdge(clk)

    for i in range(samples):
        data = int(samples_in[i])

        sample_in.value = data

        yield RisingEdge(clk)

        #print int(dut.out3)
        samples_out[i] = sample_out.value.signed_integer
    print(sample_out.value.binstr)


    plt.plot(t, samples_out,alpha=0.5, label="Output")
    # plt.plot(t, samples_in, label="original")

    # plt.plot(t, datain* 1024, label="PDM")

    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
    plt.xlabel('time ')
    plt.title('Basic moving average f')
    plt.grid(True)
    plt.savefig("test.png")
    plt.show()



