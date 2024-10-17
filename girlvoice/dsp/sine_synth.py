import numpy as np
from amaranth import *
import amaranth.lib.wiring as wiring
from amaranth.lib.wiring import In, Out
from amaranth.lib import stream

class StaticSineSynth(wiring.Component):

    def __init__(self, frequency, fs, sample_width):

        assert frequency <= fs/2

        super().__init__({
            "en": In(1),
            "source": Out(stream.Signature(signed(sample_width), always_valid=True))
        })

        self.sample_width = sample_width
        self.frequency = frequency
        self.fs = fs

        self.N = int(self.fs / self.frequency)
        print(f"Target synth freq: {self.frequency}, actual: {fs / self.N}")

    def elaborate(self, platform):
        m = Module()

        N = self.N

        t = np.linspace(0, 2*np.pi, N)
        y = np.sin(t)
        y_norm = y * (2**self.sample_width)
        print(t)
        print(y_norm)
        ring = Array([C(int(y_i), signed(self.sample_width)) for y_i in y_norm])

        idx = Signal(range(N), reset=0)

        with m.If(self.en):
            m.d.comb += self.source.payload.eq(ring[idx])
            with m.If(self.source.ready):
                with m.If(idx < N):
                    m.d.sync += idx.eq(idx+1)
                with m.Else():
                    m.d.sync += idx.eq(0)

        return m


