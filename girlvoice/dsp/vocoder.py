#!/usr/bin/env python
from math import log
import numpy as np
from scipy import signal
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream
from amaranth.sim import Simulator

from girlvoice.dsp.sine_synth import ParallelSineSynth
from girlvoice.dsp.vga import VariableGainAmp
from girlvoice.dsp.bandpass_iir import BandpassIIR
from girlvoice.dsp.envelope import EnvelopeFollower
from girlvoice.dsp.envelope_vga import EnvelopeVGA
from girlvoice.dsp.tdm_slice import TDMMultiply
from girlvoice.stream import stream_get, stream_put

class ThreadedVocoderChannel(wiring.Component):
    def __init__(self, channel_edges, fs=48000, sample_width=18, mult_slice: TDMMultiply = None):
        self.fs = fs
        self.sample_width = sample_width

        if mult_slice is None:
            self.mult = TDMMultiply(sample_width=sample_width, num_threads=3)
        else:
            self.mult = mult_slice
        self.bandpass = BandpassIIR(
            band_edges=channel_edges,
            filter_order=1,
            sample_width=sample_width,
            fs=fs,
            mult_slice=self.mult
        )
        self.vga = VariableGainAmp(sample_width, sample_width, mult_slice=self.mult)
        self.envelope = EnvelopeFollower(sample_width, attack_halflife=.1, decay_halflife=25, mult_slice=self.mult)
        # self.env_vga = EnvelopeVGA(sample_width, fs=fs, attack_halflife=1, decay_halflife=20, mult_slice=self.mult)

        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "carrier": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })

    def elaborate(self, platform):
        m = Module()

        m.submodules.mult = self.mult
        m.submodules.bandpass = self.bandpass
        # m.submodules.env_vga = self.env_vga
        m.submodules.vga = self.vga
        m.submodules.envelope = self.envelope

        wiring.connect(m, wiring.flipped(self.sink), self.bandpass.sink)
        wiring.connect(m, self.bandpass.source, self.envelope.sink)
        wiring.connect(m, self.envelope.source, self.vga.modulator)
        wiring.connect(m, wiring.flipped(self.carrier), self.vga.carrier)

        wiring.connect(m, wiring.flipped(self.source), self.vga.source)

        # wiring.connect(m, self.bandpass.source, self.env_vga.sink)
        # wiring.connect(m, wiring.flipped(self.carrier), self.env_vga.carrier)

        # wiring.connect(m, wiring.flipped(self.source), self.env_vga.source)

        return m

class StaticVocoderChannel(wiring.Component):
    def __init__(self, channel_edges, fs=48000, sample_width=18):
        self.fs = fs
        self.channel_freq = channel_edges[0] + (channel_edges[1] - channel_edges[0])/2
        self.sample_width = sample_width

        # self.vga = VariableGainAmp(sample_width, sample_width)
        # self.synth = StaticSineSynth(self.channel_freq, fs, clk_sync_freq, sample_width)
        self.bandpass = BandpassIIR(
            band_edges=channel_edges,
            filter_order=1,
            sample_width=sample_width,
            fs=fs
        )
        self.env_vga = EnvelopeVGA(sample_width, fs=fs, attack_halflife=1, decay_halflife=20)
        # self.envelope = EnvelopeFollower(sample_width, attack_halflife=1, decay_halflife=20)

        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "carrier": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })

    def elaborate(self, platform):
        m = Module()

        # m.submodules.vga = self.vga
        m.submodules.bandpass = self.bandpass
        # m.submodules.envelope = self.envelope
        m.submodules.env_vga = self.env_vga

        wiring.connect(m, wiring.flipped(self.sink), self.bandpass.sink)
        wiring.connect(m, self.bandpass.source, self.env_vga.sink)
        # wiring.connect(m, self.envelope.source, self.vga.modulator)
        wiring.connect(m, wiring.flipped(self.carrier), self.env_vga.carrier)

        wiring.connect(m, wiring.flipped(self.source), self.env_vga.source)


        return m

class ChannelDemux(wiring.Component):
    def __init__(self, num_channels, sample_width):
        self.sample_width = sample_width
        self.num_channels = num_channels

        signature = {
            "sink": In(stream.Signature(signed(sample_width)))
        }
        for i in range(num_channels):
            signature[f"ch_source_{i}"] = Out(stream.Signature(signed(sample_width)))

        super().__init__(signature=signature)

    def source(self, i):
        return self.__dict__[f"ch_source_{i}"]

    def elaborate(self, platform):
        m = Module()

        ch_readys = Signal(self.num_channels)

        # The module sink is ready when all channel sinks are ready
        m.d.comb += self.sink.ready.eq(ch_readys.all())
        for i in range(self.num_channels):
            ch_source = self.source(i)
            m.d.comb += [
                # Connect the module sink to all channel sinks,
                # channel inputs are valid when the module sink is valid and all channels are ready
                ch_source.payload.eq(self.sink.payload),
                ch_source.valid.eq(self.sink.valid & self.sink.ready),
                ch_readys.bit_select(i, 1).eq(ch_source.ready),
            ]

        return m

class ChannelMux(wiring.Component):
    def __init__(self, num_channels, sample_width):
        self.sample_width = sample_width
        self.num_channels = num_channels

        signature = {
            "source": Out(stream.Signature(signed(sample_width)))
        }
        for i in range(num_channels):
            signature[f"ch_sink_{i}"] = In(stream.Signature(signed(sample_width)))

        super().__init__(signature=signature)

    def sink(self, i):
        return self.__dict__[f"ch_sink_{i}"]

    def elaborate(self, platform):
        m = Module()

        acc_width = self.sample_width + self.num_channels
        acc = Signal(signed(acc_width))
        m.d.comb += self.source.payload.eq(acc)

        idx = Signal(range(self.num_channels + 1))

        ch_sink_mux = Array([self.sink(i) for i in range(self.num_channels)])
        cur_sample = Signal(self.sample_width)
        next_sample = Signal(self.sample_width)

        ch_valids = Signal(self.num_channels)
        m.d.comb += [ch_valids.bit_select(i, 1).eq(self.sink(i).valid) for i in range(self.num_channels)]
        all_ch_valid = Signal()
        m.d.comb += all_ch_valid.eq(ch_valids.all())

        m.d.comb += next_sample.eq(ch_sink_mux[idx].payload)

        cur_ready = Signal()
        m.d.comb += ch_sink_mux[idx].ready.eq(cur_ready)
        with m.FSM():
            with m.State("GET_NEXT_SAMPLE"):
                with m.If(all_ch_valid):
                    m.d.sync += cur_ready.eq(1)
                    m.d.sync += cur_sample.eq(next_sample)
                    m.next = "SUM"
            with m.State("SUM"):
                m.d.sync += acc.eq(acc + cur_sample)
                m.d.sync += cur_sample.eq(ch_sink_mux[idx + 1].payload)
                with m.If(idx == self.num_channels):
                    m.d.sync += cur_ready.eq(0)
                    m.d.sync += idx.eq(0)
                    m.d.sync += self.source.valid.eq(1)
                    m.next = "WAIT"
                with m.Else():
                    m.d.sync += idx.eq(idx + 1)
                    # m.next = "GET_NEXT_SAMPLE"

            with m.State("WAIT"):
                with m.If(self.source.ready == 1):
                    m.d.sync += acc.eq(0)
                    m.d.sync += self.source.valid.eq(0)
                    m.next = "GET_NEXT_SAMPLE"

        return m

def mel(freq):
    return 1127 * log(1 + (freq/700))

def mel_to_freq(mel):
    return 700 * (np.exp(mel/1127) - 1)

class StaticVocoder(wiring.Component):
    def __init__(self, start_freq, end_freq, num_channels, clk_sync_freq, channel_class=StaticVocoderChannel, fs=48000, sample_width=18):
        self.sample_width = sample_width
        self.num_channels = num_channels
        self.fs = fs

        self.ch_edges = []

        # Taken from Stanford ECE Vocoder github. This is calculated based on mel scale spacing
        bandwidth_param = 0.035

        start_mel = mel(start_freq)
        end_mel = mel(end_freq)

        print(f"Channel range as mel {start_mel}-{end_mel}")

        ch_mel, channel_space = np.linspace(start_mel, end_mel, num_channels, retstep=True)
        self.ch_freq = mel_to_freq(ch_mel)

        print(f"Channel center frequencies: {self.ch_freq}")

        for freq in self.ch_freq:
            ch_start = freq * (1 - bandwidth_param)
            ch_end = freq * (1 + bandwidth_param)
            self.ch_edges.append([ch_start, ch_end])

        print(f"Generating vocoder channels at {self.ch_edges} Hz")

        mults_per_channel = 2
        self.num_slices = self.num_channels // 2
        # self.slices = [TDMMultiply(sample_width=sample_width, num_threads=2 * mults_per_channel) for _ in range(self.num_slices)]

        self.synth = ParallelSineSynth(self.ch_freq, fs, sample_width)

        self.channels = []
        for i in range(len(self.ch_freq)):
            edges = self.ch_edges[i]
            # slice = self.slices[i//2]
            self.channels.append(channel_class(
                channel_edges=edges,
                fs=fs,
                sample_width=sample_width,
                # mult_slice=slice
            ))

        self.demux = ChannelDemux(num_channels=num_channels, sample_width=sample_width)
        self.mux = ChannelMux(num_channels=num_channels, sample_width=sample_width)

        freqs = np.linspace(0, int(self.ch_freq[-1]), int(fs))
        for ch in self.channels:
            a = ch.bandpass.a_quant
            b = ch.bandpass.b_quant
            w, q = signal.freqz(b=b, a=a, fs=fs)

        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })

    def elaborate(self, platform):
        m = Module()
        m.submodules.synth = self.synth
        m.submodules.mux = self.mux
        m.submodules.demux = self.demux

        wiring.connect(m, wiring.flipped(self.sink), self.demux.sink)
        wiring.connect(m, wiring.flipped(self.source), self.mux.source)

        for i in range(self.num_channels):
            ch = self.channels[i]
            m.submodules += ch

            wiring.connect(m, self.demux.source(i), ch.sink)
            wiring.connect(m, self.mux.sink(i), ch.source)
            wiring.connect(m, self.synth.source(i), ch.carrier)

        return m

def demux_sim():
    clk_freq = 60e6
    bit_width = 16
    num_channels = 16
    dut = ChannelDemux(num_channels=num_channels, bit_width=bit_width)

    test_samples = [1, 2, 3, 4, 5]

    async def tb(ctx):
        for sample in test_samples:
            await stream_put(ctx, dut.sink, sample)


    sim = Simulator()
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)

if __name__ == "__main__":
    demux_sim()