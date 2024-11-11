from cmath import phase
from math import exp, log
from click import BadArgumentUsage
import numpy as np
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream
from scipy import signal

from girlvoice.dsp.sine_synth import StaticSineSynth
from girlvoice.dsp.vga import VariableGainAmp
from girlvoice.dsp.bandpass_iir import BandpassIIR
from girlvoice.dsp.envelope import EnvelopeFollower


class StaticVocoderChannel(wiring.Component):
    def __init__(self, channel_edges, clk_sync_freq, fs=48000, sample_width=18):
        self.fs = fs
        self.channel_freq = channel_edges[0] + (channel_edges[1] - channel_edges[0])/2
        self.sample_width = sample_width

        self.vga = VariableGainAmp(sample_width, sample_width)
        self.synth = StaticSineSynth(self.channel_freq, fs, clk_sync_freq, sample_width)
        self.bandpass = BandpassIIR(
            band_edges=channel_edges,
            filter_order=1,
            sample_width=sample_width,
            fs=fs
        )

        self.envelope = EnvelopeFollower(sample_width, attack_halflife=1, decay_halflife=20)

        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })

    def elaborate(self, platform):
        m = Module()

        m.submodules.vga = self.vga
        m.submodules.synth = self.synth
        m.submodules.bandpass = self.bandpass
        m.submodules.envelope = self.envelope

        wiring.connect(m, wiring.flipped(self.sink), self.bandpass.sink)
        wiring.connect(m, self.bandpass.source, self.envelope.sink)
        wiring.connect(m, self.envelope.source, self.vga.modulator)
        wiring.connect(m, self.synth.source, self.vga.carrier)

        wiring.connect(m, wiring.flipped(self.source), self.vga.source)
        # wiring.connect(m, wiring.flipped(self.source), self.envelope.source)
        # wiring.connect(m, wiring.flipped(self.source), self.bandpass.source)

        m.d.comb += self.synth.en.eq(1)

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

        print(f"Generating frequency synth LUT")
        # phase_bit_width = 4
        # t = np.linspace(0, 2*np.pi, 2**phase_bit_width)
        # y = np.sin(t)
        # lut = Array(C(int(y_i*(2**(sample_width-1))), signed(sample_width)) for y_i in y)

        self.channels = [channel_class(channel_edges=edges, fs=fs, sample_width=sample_width, clk_sync_freq=clk_sync_freq) for edges in self.ch_edges]

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

        acc_width = self.sample_width + self.num_channels
        acc = Signal(signed(acc_width))
        m.d.comb += self.source.payload.eq(acc)

        ch_readys = Signal(self.num_channels)
        for i in range(self.num_channels):
            ch = self.channels[i]
            m.submodules += ch
            m.d.comb += ch.sink.payload.eq(self.sink.payload)
            m.d.comb += ch.sink.valid.eq(self.sink.valid & self.sink.ready)
            m.d.comb += ch_readys.bit_select(i, 1).eq(ch.sink.ready)

        m.d.comb += self.sink.ready.eq(ch_readys.all())

        idx = Signal(range(self.num_channels))

        source_mux = Array([ch.source for ch in self.channels])

        with m.FSM():
            with m.State("SUM"):
                m.d.comb += self.source.valid.eq(0)
                with m.If(source_mux[idx].valid):
                    m.d.comb += source_mux[idx].ready.eq(1)
                    m.d.sync += acc.eq(acc + source_mux[idx].payload)

                    with m.If(idx >= self.num_channels - 1):
                        m.d.sync += idx.eq(0)
                        m.next = "WAIT"
                    with m.Else():
                        m.d.sync += idx.eq(idx + 1)

            with m.State("WAIT"):
                m.d.comb += self.source.valid.eq(1)
                with m.If(self.source.ready == 1):
                    m.d.sync += acc.eq(0)
                    m.next = "SUM"

        return m