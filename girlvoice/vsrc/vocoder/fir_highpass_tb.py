from scipy import signal
import numpy as np
import matplotlib.pyplot as plt
import cocotb
from cocotb.triggers import RisingEdge
from cocotb.clock import Clock


class filter_tb:
    def __init__(self, dut, iw: int, ow: int, tw: int, ntaps: int) -> None:
        self.dut = dut
        self.iw = iw
        self.ow = ow
        self.ntaps = ntaps

        self.i_clk = dut.clk
        self.i_sample_in = dut.sample_in
        self.i_sample_out = dut.sample_out
        self.i_reset = dut.reset


    async def load(self, ntaps: int, data):
        pass

    async def reset(self):
        self.i_sample_in.value = 0
        self.i_clk.value = 0
        self.i_reset.value = 1
        await RisingEdge(self.i_clk)
        self.i_reset = 0
        await RisingEdge(self.i_clk)
        pass

    async def apply(self, nlen: int, data):
        pass


@cocotb.test()
def hp_fir(dut):
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

    tap_coefficients = [  -2304,
    1727,
    1372,
    1097,
    746,
    225,
    -502,
    -1404,
    -2401,
    -3378,
    -4201,
    -4752,
    27827,
    -4752,
    -4201,
    -3378,
    -2401,
    -1404,
    -502,
    225,
    746,
    1097,
    1372,
    1727,
    -2304]
    cocotb.fork(Clock(dut.clk,5000).start())

    yield RisingEdge(clk)

    load_taps(dut, len(tap_coefficients), tap_coefficients)

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
    # print(sample_out.value.binstr)


    # plt.plot(t, samples_out,alpha=0.5, label="Output")
    # # plt.plot(t, samples_in, label="original")

    # # plt.plot(t, datain* 1024, label="PDM")

    # plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0.)
    # plt.xlabel('time ')
    # plt.title('Basic moving average f')
    # plt.grid(True)
    # plt.savefig("test.png")
    # plt.show()



async def load_taps(dut, ntaps, data):
    clk = dut.clk
    i_tap_wr = dut.i_tap_wr

    i_tap_wr.value = 1
    for i in range(ntaps):
        dut.i_tap.value = data[i]
        await RisingEdge(clk)

    i_tap_wr.value = 0


