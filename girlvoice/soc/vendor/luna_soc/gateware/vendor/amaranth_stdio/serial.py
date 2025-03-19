from amaranth import *
from amaranth.lib import enum, data, wiring
from amaranth.lib.wiring import In, Out, connect, flipped
from amaranth.lib.cdc import FFSynchronizer
from amaranth.utils import bits_for


__all__ = ["Parity", "AsyncSerialRX", "AsyncSerialTX", "AsyncSerial"]


class Parity(enum.Enum):
    """Asynchronous serial parity mode."""
    NONE  = "none"
    MARK  = "mark"
    SPACE = "space"
    EVEN  = "even"
    ODD   = "odd"

    def _compute_bit(self, data):
        cast_data = Value.cast(data)
        if self == self.NONE:
            return Const(0, 0)
        if self == self.MARK:
            return Const(1, 1)
        if self == self.SPACE:
            return Const(0, 1)
        if self == self.EVEN:
            return cast_data.xor()
        if self == self.ODD:
            return ~cast_data.xor()
        assert False # :nocov:


class _FrameLayout(data.StructLayout):
    def __init__(self, data_bits, parity):
        super().__init__({
            "start":  unsigned(1),
            "data":   unsigned(data_bits),
            "parity": unsigned(0 if parity == Parity.NONE else 1),
            "stop":   unsigned(1),
        })


class AsyncSerialRX(wiring.Component):
    class Signature(wiring.Signature):
        """Asynchronous serial receiver signature.

        Parameters
        ----------
        divisor : int
            Clock divisor initial value. Should be set to ``int(clk_frequency // baudrate)``.
        divisor_bits : int
            Clock divisor width. Optional. If omitted, ``bits_for(divisor)`` is used instead.
        data_bits : int
            Data bits per frame.
        parity : :class:`Parity`
            Parity mode.

        Interface attributes
        --------------------
        divisor : Signal, in
            Clock divisor.
        data : Signal, out
            Read data. Valid only when ``rdy`` is asserted.
        err.overflow : Signal, out
            Error flag. A new frame has been received, but the previous one was not acknowledged.
        err.frame : Signal, out
            Error flag. The received bits do not fit in a frame.
        err.parity : Signal, out
            Error flag. The parity check has failed.
        rdy : Signal, out
            Read strobe.
        ack : Signal, in
            Read acknowledge. Must be held asserted while data can be read out of the receiver.
        i : Signal, in
            Serial input.

        Raises
        ------
        See :meth:`AsyncSerialRX.Signature.check_parameters`.
        """
        def __init__(self, *, divisor, divisor_bits=None, data_bits=8, parity="none"):
            self.check_parameters(divisor=divisor, divisor_bits=divisor_bits, data_bits=data_bits,
                                  parity=parity)
            self._divisor      = divisor
            self._divisor_bits = divisor_bits if divisor_bits is not None else bits_for(divisor)
            self._data_bits    = data_bits
            self._parity       = Parity(parity)

            super().__init__({
                "divisor": In(unsigned(self._divisor_bits), init=self._divisor),
                "data":    Out(unsigned(self._data_bits)),
                "err":     Out(data.StructLayout({"overflow": 1, "frame": 1, "parity": 1})),
                "rdy":     Out(unsigned(1)),
                "ack":     In(unsigned(1)),
                "i":       In(unsigned(1), init=1),
            })

        @classmethod
        def check_parameters(cls, *, divisor, divisor_bits=None, data_bits=8, parity="none"):
            """Validate signature parameters.

            Raises
            ------
            :exc:`TypeError`
                If ``divisor`` is not an integer greater than or equal to 5.
            :exc:`TypeError`
                If ``divisor_bits`` is not `None` and not an integer greater than or equal to
                ``bits_for(divisor)``.
            :exc:`TypeError`
                If ``data_bits`` is not an integer greater than or equal to 0.
            :exc:`ValueError`
                If ``parity`` is not a :class:`Parity` member.
            """
            # The clock divisor must be >= 5 to keep the receiver FSM synchronized with its input
            # during a DONE->IDLE->BUSY transition.
            AsyncSerial.Signature._check_divisor(divisor, divisor_bits, min_divisor=5)
            if not isinstance(data_bits, int) or data_bits < 0:
                raise TypeError(f"Data bits must be a non-negative integer, not {data_bits!r}")
            # Raise a ValueError if parity is invalid.
            Parity(parity)

        @property
        def divisor(self):
            return self._divisor

        @property
        def divisor_bits(self):
            return self._divisor_bits

        @property
        def data_bits(self):
            return self._data_bits

        @property
        def parity(self):
            return self._parity

        def __eq__(self, other):
            """Compare signatures.

            Two signatures are equal if they have the same divisor value, divisor bits,
            data bits, and parity.
            """
            return (isinstance(other, AsyncSerialRX.Signature) and
                    self.divisor == other.divisor and
                    self.divisor_bits == other.divisor_bits and
                    self.data_bits == other.data_bits and
                    self.parity == other.parity)

        def __repr__(self):
            return f"AsyncSerialRX.Signature({self.members!r})"

    """Asynchronous serial receiver.

    Parameters
    ----------
    divisor : int
        Clock divisor initial value. Should be set to ``int(clk_frequency // baudrate)``.
    divisor_bits : int
        Clock divisor width. Optional. If omitted, ``bits_for(divisor)`` is used instead.
    data_bits : int
        Data bits per frame.
    parity : :class:`Parity`
        Parity mode.
    pins : :class:`amaranth.lib.io.Pin`
        UART pins. Optional. See :class:`amaranth_boards.resources.UARTResource` for layout.
        If provided, the ``i`` port of the receiver is internally connected to ``pins.rx.i``.

    Raises
    ------
    See :meth:`AsyncSerialRX.Signature.check_parameters`.
    """
    def __init__(self, *, divisor, divisor_bits=None, data_bits=8, parity="none", pins=None):
        super().__init__(self.Signature(divisor=divisor, divisor_bits=divisor_bits,
                                        data_bits=data_bits, parity=parity))
        self._pins = pins

    def elaborate(self, platform):
        m = Module()

        timer = Signal.like(self.divisor)
        shreg = Signal(_FrameLayout(len(self.data), self.signature.parity))
        bitno = Signal(range(len(shreg.as_value())))

        if self._pins is not None:
            m.submodules += FFSynchronizer(self._pins.rx.i, self.i, init=1)

        with m.FSM() as fsm:
            with m.State("IDLE"):
                with m.If(~self.i):
                    m.d.sync += [
                        bitno.eq(len(shreg.as_value()) - 1),
                        timer.eq(self.divisor >> 1),
                    ]
                    m.next = "BUSY"

            with m.State("BUSY"):
                with m.If(timer != 0):
                    m.d.sync += timer.eq(timer - 1)
                with m.Else():
                    m.d.sync += [
                        shreg.eq(Cat(shreg.as_value()[1:], self.i)),
                        bitno.eq(bitno - 1),
                        timer.eq(self.divisor - 1),
                    ]
                    with m.If(bitno == 0):
                        m.next = "DONE"

            with m.State("DONE"):
                with m.If(self.ack):
                    m.d.sync += [
                        self.data.eq(shreg.data),
                        self.err.frame .eq(~((shreg.start == 0) & (shreg.stop == 1))),
                        self.err.parity.eq(~(shreg.parity ==
                                             self.signature.parity._compute_bit(shreg.data))),
                    ]
                m.d.sync += self.err.overflow.eq(~self.ack)
                m.next = "IDLE"

        with m.If(self.ack):
            m.d.sync += self.rdy.eq(fsm.ongoing("DONE"))

        return m


class AsyncSerialTX(wiring.Component):
    class Signature(wiring.Signature):
        """Asynchronous serial transmitter signature.

        Parameters
        ----------
        divisor : int
            Clock divisor initial value. Should be set to ``int(clk_frequency // baudrate)``.
        divisor_bits : int
            Clock divisor width. Optional. If omitted, ``bits_for(divisor)`` is used instead.
        data_bits : int
            Data bits per frame.
        parity : :class:`Parity`
            Parity mode.

        Interface attributes
        --------------------
        divisor : Signal, in
            Clock divisor.
        data : Signal, in
            Write data. Valid only when ``ack`` is asserted.
        rdy : Signal, out
            Write ready. Asserted when the transmitter is ready to transmit data.
        ack : Signal, in
            Write strobe. Data gets transmitted when both ``rdy`` and ``ack`` are asserted.
        o : Signal, out
            Serial output.

        Raises
        ------
        See :meth:`AsyncSerialTX.Signature.check_parameters`.
        """
        def __init__(self, *, divisor, divisor_bits=None, data_bits=8, parity="none"):
            self.check_parameters(divisor=divisor, divisor_bits=divisor_bits, data_bits=data_bits,
                                  parity=parity)
            self._divisor      = divisor
            self._divisor_bits = divisor_bits if divisor_bits is not None else bits_for(divisor)
            self._data_bits    = data_bits
            self._parity       = Parity(parity)

            super().__init__({
                "divisor": In(unsigned(self._divisor_bits), init=self._divisor),
                "data":    In(unsigned(self._data_bits)),
                "rdy":     Out(unsigned(1)),
                "ack":     In(unsigned(1)),
                "o":       Out(unsigned(1), init=1),
            })

        @classmethod
        def check_parameters(cls, *, divisor, divisor_bits=None, data_bits=8, parity="none"):
            """Validate signature parameters.

            Raises
            ------
            :exc:`TypeError`
                If ``divisor`` is not an integer greater than or equal to 1.
            :exc:`TypeError`
                If ``divisor_bits`` is not `None` and not an integer greater than or equal to
                ``bits_for(divisor)``.
            :exc:`TypeError`
                If ``data_bits`` is not an integer greater than or equal to 0.
            :exc:`ValueError`
                If ``parity`` is not a :class:`Parity` member.
            """
            AsyncSerial.Signature._check_divisor(divisor, divisor_bits, min_divisor=1)
            if not isinstance(data_bits, int) or data_bits < 0:
                raise TypeError(f"Data bits must be a non-negative integer, not {data_bits!r}")
            # Raise a ValueError if parity is invalid.
            Parity(parity)

        @property
        def divisor(self):
            return self._divisor

        @property
        def divisor_bits(self):
            return self._divisor_bits

        @property
        def data_bits(self):
            return self._data_bits

        @property
        def parity(self):
            return self._parity

        def __eq__(self, other):
            """Compare signatures.

            Two signatures are equal if they have the same divisor value, divisor bits,
            data bits, and parity.
            """
            return (isinstance(other, AsyncSerialTX.Signature) and
                    self.divisor == other.divisor and
                    self.divisor_bits == other.divisor_bits and
                    self.data_bits == other.data_bits and
                    self.parity == other.parity)

        def __repr__(self):
            return f"AsyncSerialTX.Signature({self.members!r})"

    """Asynchronous serial transmitter.

    Parameters
    ----------
    divisor : int
        Clock divisor initial value. Should be set to ``int(clk_frequency // baudrate)``.
    divisor_bits : int
        Clock divisor width. Optional. If omitted, ``bits_for(divisor)`` is used instead.
    data_bits : int
        Data bits per frame.
    parity : :class:`Parity`
        Parity mode.
    pins : :class:`amaranth.lib.io.Pin`
        UART pins. Optional. See :class:`amaranth_boards.resources.UARTResource` for layout.
        If provided, the ``o`` port of the transmitter is internally connected to ``pins.tx.o``.

    Raises
    ------
    See :class:`AsyncSerialTX.Signature.check_parameters`.
    """
    def __init__(self, *, divisor, divisor_bits=None, data_bits=8, parity="none", pins=None):
        super().__init__(signature=self.Signature(divisor=divisor, divisor_bits=divisor_bits,
                                                  data_bits=data_bits, parity=parity))
        self._pins = pins

    def elaborate(self, platform):
        m = Module()

        timer = Signal.like(self.divisor)
        shreg = Signal(_FrameLayout(len(self.data), self.signature.parity))
        bitno = Signal(range(len(shreg.as_value())))

        if self._pins is not None:
            m.d.comb += self._pins.tx.o.eq(self.o)

        with m.FSM():
            with m.State("IDLE"):
                m.d.comb += self.rdy.eq(1)
                with m.If(self.ack):
                    m.d.sync += [
                        shreg.start .eq(0),
                        shreg.data  .eq(self.data),
                        shreg.parity.eq(self.signature.parity._compute_bit(self.data)),
                        shreg.stop  .eq(1),
                        bitno.eq(len(shreg.as_value()) - 1),
                        timer.eq(self.divisor - 1),
                    ]
                    m.next = "BUSY"

            with m.State("BUSY"):
                with m.If(timer != 0):
                    m.d.sync += timer.eq(timer - 1)
                with m.Else():
                    m.d.sync += [
                        Cat(self.o, shreg).eq(shreg),
                        bitno.eq(bitno - 1),
                        timer.eq(self.divisor - 1),
                    ]
                    with m.If(bitno == 0):
                        m.next = "IDLE"

        return m


class AsyncSerial(wiring.Component):
    class Signature(wiring.Signature):
        """Asynchronous serial transceiver signature.

        Parameters
        ----------
        divisor : int
            Clock divisor initial value. Should be set to ``int(clk_frequency // baudrate)``.
        divisor_bits : int
            Clock divisor width. Optional. If omitted, ``bits_for(divisor)`` is used instead.
        data_bits : int
            Data bits per frame.
        parity : :class:`Parity`
            Parity mode.

        Interface attributes
        --------------------
        divisor : Signal, in
            Clock divisor. It is internally connected to ``rx.divisor`` and ``tx.divisor``.
        rx : :class:`wiring.Interface`
            Receiver interface. See :class:`AsyncSerialRX.Signature`.
        tx : :class:`wiring.Interface`
            Transmitter interface. See :class:`AsyncSerialTX.Signature`.

        Raises
        ------
        See :meth:`AsyncSerial.Signature.check_parameters`.
        """
        def __init__(self, *, divisor, divisor_bits=None, data_bits=8, parity="none"):
            rx_sig = AsyncSerialRX.Signature(divisor=divisor, divisor_bits=divisor_bits,
                                             data_bits=data_bits, parity=parity)
            tx_sig = AsyncSerialTX.Signature(divisor=divisor, divisor_bits=divisor_bits,
                                             data_bits=data_bits, parity=parity)

            assert rx_sig.members["divisor"] == tx_sig.members["divisor"]
            divisor_shape = rx_sig.members["divisor"].shape
            divisor_init  = rx_sig.members["divisor"].init

            super().__init__({
                "divisor": In(divisor_shape, init=divisor_init),
                "rx":      Out(rx_sig),
                "tx":      Out(tx_sig),
            })

        @classmethod
        def _check_divisor(cls, divisor, divisor_bits, min_divisor=1):
            if not isinstance(divisor, int) or divisor < min_divisor:
                raise TypeError(f"Divisor initial value must be an integer greater than or equal "
                                f"to {min_divisor}, not {divisor!r}")
            if divisor_bits is not None:
                min_divisor_bits = bits_for(divisor)
                if not isinstance(divisor_bits, int) or divisor_bits < min_divisor_bits:
                    raise TypeError(f"Divisor bits must be an integer greater than or equal to "
                                    f"{min_divisor_bits}, not {divisor_bits!r}")

        @classmethod
        def check_parameters(cls, *, divisor, divisor_bits=None, data_bits=8, parity="none"):
            """Validate signature parameters.

            Raises
            ------
            :exc:`TypeError`
                If ``divisor`` is not an integer greater than or equal to 5.
            :exc:`TypeError`
                If ``divisor_bits`` is not `None` and not an integer greater than or equal to
                ``bits_for(divisor)``.
            :exc:`TypeError`
                If ``data_bits`` is not an integer greater than or equal to 0.
            :exc:`ValueError`
                If ``parity`` is not a :class:`Parity` member.
            """
            AsyncSerialRX.Signature.check_parameters(divisor=divisor, divisor_bits=divisor_bits,
                                                     data_bits=data_bits, parity=parity)
            AsyncSerialTX.Signature.check_parameters(divisor=divisor, divisor_bits=divisor_bits,
                                                     data_bits=data_bits, parity=parity)

        @property
        def divisor(self):
            return self.members["rx"].signature.divisor

        @property
        def divisor_bits(self):
            return self.members["rx"].signature.divisor_bits

        @property
        def data_bits(self):
            return self.members["rx"].signature.data_bits

        @property
        def parity(self):
            return self.members["rx"].signature.parity

        def __eq__(self, other):
            """Compare signatures.

            Two signatures are equal if they have the same divisor value, divisor bits,
            data bits, and parity.
            """
            return (isinstance(other, AsyncSerial.Signature) and
                    self.divisor == other.divisor and
                    self.divisor_bits == other.divisor_bits and
                    self.data_bits == other.data_bits and
                    self.parity == other.parity)

        def __repr__(self):
            return f"AsyncSerial.Signature({self.members!r})"

    """Asynchronous serial transceiver.

    Parameters
    ----------
    divisor : int
        Clock divisor initial value. Should be set to ``int(clk_frequency // baudrate)``.
    divisor_bits : int
        Clock divisor width. Optional. If omitted, ``bits_for(divisor)`` is used instead.
    data_bits : int
        Data bits per frame.
    parity : :class:`Parity`
        Parity mode.
    pins : :class:`amaranth.lib.io.Pin`
        UART pins. Optional. See :class:`amaranth_boards.resources.UARTResource` for layout.
        If provided, the ``rx.i`` and ``tx.o`` ports of the transceiver are internally connected
        to ``pins.rx.i`` and ``pins.tx.o``, respectively.

    Raises
    ------
    See :meth:`AsyncSerial.Signature.check_parameters`.
    """
    def __init__(self, *, divisor, divisor_bits=None, data_bits=8, parity="none", pins=None):
        super().__init__(self.Signature(divisor=divisor, divisor_bits=divisor_bits,
                                        data_bits=data_bits, parity=parity))
        self._pins = pins

    def elaborate(self, platform):
        m = Module()

        rx = AsyncSerialRX(divisor=self.signature.divisor,
                           divisor_bits=self.signature.divisor_bits,
                           data_bits=self.signature.data_bits,
                           parity=self.signature.parity)
        tx = AsyncSerialTX(divisor=self.signature.divisor,
                           divisor_bits=self.signature.divisor_bits,
                           data_bits=self.signature.data_bits,
                           parity=self.signature.parity)
        m.submodules.rx = rx
        m.submodules.tx = tx

        m.d.comb += [
            self.rx.divisor.eq(self.divisor),
            self.tx.divisor.eq(self.divisor),
        ]

        if self._pins is not None:
            m.submodules += FFSynchronizer(self._pins.rx.i, self.rx.i, init=1)
            m.d.comb += self._pins.tx.o.eq(self.tx.o)

        connect(m, flipped(self.rx), rx)
        connect(m, flipped(self.tx), tx)

        return m
