from migen import *

from litex.gen import *
from litex.soc.interconnect.stream import Endpoint
from litex.soc.interconnect.csr import *
import amaranth.back.verilog as verilog

import girlvoice.dsp.vocoder as vocoder


class StaticVocoder(LiteXModule):

    def __init__(self, platform, start_freq, end_freq, num_channels, clk_sync_freq, channel_class=vocoder.StaticVocoderChannel, fs=48000, sample_width=18):
        self.sink = sink = Endpoint([("data", sample_width)])
        self.source = source = Endpoint([("data", sample_width)])

        self.attack = CSRStorage(size=32, description="Vocoder Attack Constant")
        self.decay = CSRStorage(size=32, description="Vocoder Decay Constant")

        self.am_vocoder = vocoder.StaticVocoder(
            start_freq=start_freq,
            end_freq=end_freq,
            num_channels=num_channels,
            clk_sync_freq=clk_sync_freq,
            channel_class=channel_class,
            fs=fs,
            sample_width=sample_width,
        )

        mod_name = type(self.am_vocoder).__name__

        print(list(self.am_vocoder.signature.flatten(self.am_vocoder)))

        with open(f"{mod_name}.v", "w") as f:
            f.write(verilog.convert(
                self.am_vocoder,
                name=mod_name,
                ports=[
                    self.am_vocoder.sink.ready,
                    self.am_vocoder.sink.valid,
                    self.am_vocoder.sink.payload,
                    self.am_vocoder.source.ready,
                    self.am_vocoder.source.valid,
                    self.am_vocoder.source.payload
                ],
                emit_src=False
            ))

        platform.add_source(f"{mod_name}.v")

        self.specials += Instance(
            mod_name,
            i_clk = ClockSignal(),
            i_rst = ResetSignal(),
            i_source__ready = source.ready,
            o_source__valid = source.valid,
            o_source__payload = source.data,
            o_sink__ready = sink.ready,
            i_sink__valid = sink.valid,
            i_sink__payload = sink.data
        )
