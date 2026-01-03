from amaranth import *
from amaranth.lib.wiring import In, Out, flipped, connect

from amaranth.lib import wiring
from amaranth_soc import csr
from amaranth_soc.gpio import PinSignature

class Peripheral(wiring.Component):
    class Input(csr.Register, access="r"):
        """Input register.

        This :class:`csr.Register` contains an array of ``pin_count`` read-only fields. Each field
        is 1-bit wide and driven by the input of its associated pin in the :attr:`Peripheral.pins`
        array.

        Values sampled from pin inputs go through :attr:`Peripheral.input_stages` synchronization
        stages (on a rising edge of ``ClockSignal("sync")``) before reaching the register.

        If ``pin_count`` is 8, then the register has the following fields:

        .. bitfield::
            :bits: 8

                [
                    { "name": "pin[0]", "bits": 1, "attr": "R" },
                    { "name": "pin[1]", "bits": 1, "attr": "R" },
                    { "name": "pin[2]", "bits": 1, "attr": "R" },
                    { "name": "pin[3]", "bits": 1, "attr": "R" },
                    { "name": "pin[4]", "bits": 1, "attr": "R" },
                    { "name": "pin[5]", "bits": 1, "attr": "R" },
                    { "name": "pin[6]", "bits": 1, "attr": "R" },
                    { "name": "pin[7]", "bits": 1, "attr": "R" },
                ]

        Parameters
        ----------
        pin_count : :class:`int`
            Number of GPIO pins.
        """
        def __init__(self, pin_count):
            super().__init__({
                "pin": [csr.Field(csr.action.R, unsigned(1)) for _ in range(pin_count)],
            })



    """GPI peripheral.

    Parameters
    ----------
    pin_count : :class:`int`
        Number of GPIO pins.
    addr_width : :class:`int`
        CSR bus address width.
    data_width : :class:`int`
        CSR bus data width.
    input_stages : :class:`int`
        Number of synchronization stages between pin inputs and the :class:`~Peripheral.Input`
        register. Optional. Defaults to ``2``.

    Attributes
    ----------
    bus : :class:`csr.Interface`
        CSR bus interface providing access to registers.
    pins : :class:`list` of :class:`wiring.PureInterface` of :class:`PinSignature`
        GPIO pin interfaces.
    alt_mode : :class:`Signal`
        Indicates which members of the :attr:`Peripheral.pins` array are in alternate mode.

    Raises
    ------
    :exc:`TypeError`
        If ``pin_count`` is not a positive integer.
    :exc:`TypeError`
        If ``input_stages`` is not a non-negative integer.
    """
    def __init__(self, *, pin_count, addr_width, data_width, input_stages=2):
        if not isinstance(pin_count, int) or pin_count <= 0:
            raise TypeError(f"Pin count must be a positive integer, not {pin_count!r}")
        if not isinstance(input_stages, int) or input_stages < 0:
            raise TypeError(f"Input stages must be a non-negative integer, not {input_stages!r}")

        regs = csr.Builder(addr_width=addr_width, data_width=data_width)

        self._input  = regs.add("Input",  self.Input(pin_count))

        self._bridge = csr.Bridge(regs.as_memory_map())

        super().__init__({
            "bus":      In(csr.Signature(addr_width=addr_width, data_width=data_width)),
            "pins":     In(1).array(pin_count),
            "alt_mode": Out(unsigned(pin_count)),
        })
        self.bus.memory_map = self._bridge.bus.memory_map

        self._pin_count    = pin_count
        self._input_stages = input_stages

    @property
    def pin_count(self):
        """Number of GPIO pins.

        Returns
        -------
        :class:`int`
        """
        return self._pin_count

    @property
    def input_stages(self):
        """Number of synchronization stages between pin inputs and the :class:`~Peripheral.Input`
        register.

        Returns
        -------
        :class:`int`
        """
        return self._input_stages

    def elaborate(self, platform):
        m = Module()
        m.submodules.bridge = self._bridge

        connect(m, flipped(self.bus), self._bridge.bus)

        for n, pin in enumerate(self.pins):
            pin_i_sync = pin
            for stage in range(self.input_stages):
                pin_i_sync_ff = Signal(reset_less=True, name=f"pin_{n}_i_sync_ff_{stage}")
                m.d.sync += pin_i_sync_ff.eq(pin_i_sync)
                pin_i_sync = pin_i_sync_ff
                del pin_i_sync_ff

            m.d.comb += self._input.f.pin[n].r_data.eq(pin_i_sync)

        return m
