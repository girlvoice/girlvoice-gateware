from amaranth import *
from amaranth.lib.wiring import In, Out, flipped, connect

from amaranth.lib import wiring
from amaranth_soc import csr


class Peripheral(wiring.Component):
    """
    envelope CSR peripheral with peak-hold.

    exposes envelope follower peak values as read-only CSR registers.
    write to Clear register to reset all peaks.

    parameters:
    num_channels : :class:`int`
        number of vocoder channels.
    sample_width : :class:`int`
        width of each envelope sample in bits.
    addr_width : :class:`int`
        CSR bus address width.
    data_width : :class:`int`
        CSR bus data width.
    input_stages : :class:`int`
        number of synchronization stages between envelope inputs and the register.
        Optional. Defaults to ``2``.

    attributes:
    bus : :class:`csr.Interface`
        CSR bus interface providing access to registers.
    envelopes : array of :class:`Signal`
        envelope value inputs from vocoder channels.
    valids : array of :class:`Signal`
        valid signals indicating when envelope values should be captured.
    """

    def __init__(self, *, num_channels, sample_width, addr_width, data_width, input_stages=2):
        if not isinstance(num_channels, int) or num_channels <= 0:
            raise TypeError(f"num_channels must be a positive integer, not {num_channels!r}")
        if not isinstance(sample_width, int) or sample_width <= 0:
            raise TypeError(f"sample_width must be a positive integer, not {sample_width!r}")
        if not isinstance(input_stages, int) or input_stages < 0:
            raise TypeError(f"input_stages must be a non-negative integer, not {input_stages!r}")

        self._num_channels = num_channels
        self._sample_width = sample_width
        self._input_stages = input_stages

        regs = csr.Builder(addr_width=addr_width, data_width=data_width)

        self._clear_reg = regs.add("Clear", self._ClearReg())

        self._channel_regs = []
        for i in range(num_channels):
            reg = regs.add(f"Ch{i}", self._ChannelReg(sample_width))
            self._channel_regs.append(reg)

        self._bridge = csr.Bridge(regs.as_memory_map())

        super().__init__({
            "bus": In(csr.Signature(addr_width=addr_width, data_width=data_width)),
            "envelopes": In(unsigned(sample_width)).array(num_channels),
            "valids": In(1).array(num_channels),
        })
        self.bus.memory_map = self._bridge.bus.memory_map

    class _ClearReg(csr.Register, access="w"):
        def __init__(self):
            super().__init__({"clear": csr.Field(csr.action.W, unsigned(1))})

    class _ChannelReg(csr.Register, access="r"):
        def __init__(self, sample_width):
            super().__init__({"value": csr.Field(csr.action.R, unsigned(sample_width))})

    @property
    def num_channels(self):
        return self._num_channels

    @property
    def sample_width(self):
        return self._sample_width

    @property
    def input_stages(self):
        return self._input_stages

    def elaborate(self, platform):
        m = Module()
        m.submodules.bridge = self._bridge

        connect(m, flipped(self.bus), self._bridge.bus)

        clear_all = self._clear_reg.f.clear.w_stb

        for n in range(self._num_channels):
            envelope_in = self.envelopes[n]
            valid_in = self.valids[n]

            # valid signal synchronizer
            valid_sync = valid_in
            for stage in range(self._input_stages):
                valid_sync_ff = Signal(reset_less=True, name=f"ch_{n}_valid_sync_ff_{stage}")
                m.d.sync += valid_sync_ff.eq(valid_sync)
                valid_sync = valid_sync_ff

            peak_value = Signal(self._sample_width, name=f"ch_{n}_peak")

            valid_prev = Signal(name=f"ch_{n}_valid_prev")
            m.d.sync += valid_prev.eq(valid_sync)
            valid_rising = valid_sync & ~valid_prev

            with m.If(clear_all):
                m.d.sync += peak_value.eq(0)
            with m.Elif(valid_rising):
                with m.If(envelope_in > peak_value):
                    m.d.sync += peak_value.eq(envelope_in)

            m.d.comb += self._channel_regs[n].f.value.r_data.eq(peak_value)

        return m
