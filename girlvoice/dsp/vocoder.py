import numpy as np
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream

from girlvoice.dsp.sine_synth import StaticSineSynth
from girlvoice.dsp.vga import VariableGainAmp
from girlvoice.dsp.bandpass_iir import BandpassIIR
from girlvoice.dsp.envelope import EnvelopeFollower


class StaticVocoderChannel(wiring.Component):
    def __init__(self, channel_freq, channel_width, fs=48000, sample_width=18):
        self.fs = fs
        self.channel_freq = channel_freq
        self.sample_width = sample_width

        self.vga = VariableGainAmp(sample_width, sample_width)
        self.synth = StaticSineSynth(channel_freq, fs, sample_width)
        self.bandpass = BandpassIIR(
            channel_freq,
            passband_width=channel_width,
            filter_order=2,
            sample_width=sample_width,
            fs=fs
        )

        self.envelope = EnvelopeFollower(sample_width)

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

        m.d.comb += self.synth.en.eq(1)

        return m

class StaticVocoder(wiring.Component):
    def __init__(self, start_freq, end_freq, num_channels, channel_class=StaticVocoderChannel, fs=48000, sample_width=18):
        self.sample_width = sample_width
        self.num_channels = num_channels
        self.fs = fs

        self.ch_freq, channel_space = np.linspace(start_freq, end_freq, num_channels, retstep=True)

        print(f"Generating vocoder channels at {self.ch_freq} Hz")

        self.channels = [channel_class(freq, channel_space, fs=fs, sample_width=sample_width) for freq in self.ch_freq]

        super().__init__({
            "sink": In(stream.Signature(signed(sample_width))),
            "source": Out(stream.Signature(signed(sample_width)))
        })

    def elaborate(self, platform):
        m = Module()

        acc_width = self.sample_width + self.num_channels
        acc = Signal(signed(acc_width))
        m.d.comb += self.source.payload.eq(acc >> self.num_channels)

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