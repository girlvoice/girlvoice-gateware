#
# This file is part of LUNA.
#
# Copyright (c) 2020-2024 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

import logging
import typing

from amaranth             import *
from amaranth.lib         import wiring
from amaranth.lib.wiring  import Component, In, Out

from amaranth_soc         import gpio

from ..core               import uart, usb2, spiflash


class GPIOProvider(Component):
    def __init__(self, id="user_pmod", index=0):
        self.id    = id
        self.index = index
        super().__init__({
            "pins": In(gpio.PinSignature()).array(8)
        })

    def elaborate(self, platform):
        m = Module()
        pins = platform.request(self.id, self.index)
        m.d.comb += pins.oe.eq(1)
        for n in range(8):
            m.d.comb += pins.o[n] .eq(self.pins[n].o)
            m.d.comb += self.pins[n].i .eq(pins.i[n])
            pass
        return m


class LEDProvider(Component):
    def __init__(self, id="led", pin_count=6):
        self.id        = id
        self.pin_count = pin_count
        super().__init__({
            "pins": In(gpio.PinSignature()).array(self.pin_count)
        })

    def elaborate(self, platform):
        m = Module()
        for n in range(self.pin_count):
            try:
                led = platform.request(self.id, n)
                m.d.comb += led.o.eq(self.pins[n].o)
            except:
                logging.warning(f"Platform does not support {self.id} {n}")
        return m


class ButtonProvider(Component):
    def __init__(self, id="button_user", index=0):
        self.id    = id
        self.index = index
        super().__init__({
            "pins": In(gpio.PinSignature()).array(1)
        })

    def elaborate(self, platform):
        m = Module()
        try:
            button = platform.request(self.id, self.index)
            m.d.comb += self.pins[0].i.eq(button.i[0])
        except:
            logging.warning(f"Platform does not support {self.id} {self.index}")
        return m


class UARTProvider(Component):
    def __init__(self, id="uart", index=0):
        self.id    = id
        self.index = index
        super().__init__({
            "pins": In(uart.PinSignature())
        })

    def elaborate(self, platform):
        m = Module()
        uart = platform.request(self.id, self.index)
        m.d.comb += [
            self.pins.rx .eq(uart.rx.i),
            uart.tx.o    .eq(self.pins.tx.o),
        ]
        if hasattr(uart.tx, "oe"):
            m.d.comb += uart.tx.oe.eq(self.pins.tx.oe),

        return m


class ULPIProvider(Component):
    def __init__(self, id, index=0):
        self.id    = id
        self.index = index
        super().__init__({
            "bus": In(usb2.ulpi.Signature())
        })

    def elaborate(self, platform):
        m = Module()

        ulpi = None
        if isinstance(self.id, typing.List):
            for id in self.id:
                try:
                    ulpi = platform.request(id, self.index)
                    break
                except:
                    pass
        else:
            try:
                ulpi = platform.request(self.id, self.index)
            except:
                pass

        if ulpi is None:
            logging.warning(f"Platform does not support a {self.id} {self.index} port for usb")
            return m

        m.d.comb += [
            self.bus.data.i  .eq(ulpi.data.i),
            ulpi.data.o      .eq(self.bus.data.o),
            ulpi.data.oe     .eq(self.bus.data.oe),

            # see ulpi.Signature
            # ulpi.clk.o       .eq(self.bus.clk),     # o
            # self.bus.nxt     .eq(ulpi.nxt.i),       # i
            # ulpi.stp.o       .eq(self.bus.stp),     # o
            # self.bus.dir     .eq(ulpi.dir.i),       # i
            # ulpi.rst.o       .eq(self.bus.rst),     # o

            ulpi.clk.o         .eq(self.bus.clk.o),   # o
            self.bus.nxt.i     .eq(ulpi.nxt.i),       # i
            ulpi.stp.o         .eq(self.bus.stp.o),   # o
            self.bus.dir.i     .eq(ulpi.dir.i),       # i
            ulpi.rst.o         .eq(self.bus.rst.o),   # o
        ]

        return m


class QSPIFlashProvider(Component):
    def __init__(self, id="qspi_flash", index=0):
        self.id    = id
        self.index = index
        super().__init__({
            "pins": In(spiflash.PinSignature())
        })

    def elaborate(self, platform):
        m = Module()
        qspi = platform.request(self.id, self.index)
        m.d.comb += [
            self.pins.dq.i.eq(qspi.dq.i),
            qspi.dq.oe.eq(self.pins.dq.oe),
            qspi.dq.o.eq(self.pins.dq.o),
            qspi.cs.o.eq(self.pins.cs.o),
        ]
        return m


class ApolloAdvertiserProvider(Component):
    def __init__(self, id="int", index=0):
        self.id    = id
        self.index = index
        super().__init__({
            "pins": Out(
                wiring.Signature({
                    "o" : Out(unsigned(1)),
                })
            )
        })

    def elaborate(self, platform):
        m = Module()
        try:
            int_pin = platform.request(self.id, self.index)
        except:
            logging.warning(f"Platform does not support ApolloAdvertiserPeripheral {self.id} {self.index}")
            return m
        m.d.comb += [
            int_pin.o.eq(self.pins.o),
        ]
        return m


class JtagProvider(Component):
    def __init__(self, id="jtag", index=0, with_reset=False):
        self.id         = id
        self.index      = index
        self.with_reset = with_reset
        super().__init__({
            "pins": In(
                wiring.Signature({
                    "tms" : In (unsigned(1)),
                    "tdi" : In (unsigned(1)),
                    "tdo" : Out(unsigned(1)),
                    "tck" : In (unsigned(1)),
                    "rst" : In (unsigned(1)),
                })
            )
        })

    def elaborate(self, platform):
        m = Module()
        try:
            jtag = platform.request(self.id, self.index)
        except:
            logging.warning(f"Platform does not support jtag port {self.id} {self.index}")
            return m

        m.d.comb += [
            self.pins.tms  .eq(jtag.tms.i),
            self.pins.tdi  .eq(jtag.tdi.i),
            jtag.tdo.o     .eq(self.pins.tdo),
            self.pins.tck  .eq(jtag.tck.i),
        ]
        if self.with_reset:
            m.d.comb += self.pins.rst.eq(self.soc.cpu.ext_reset),

        return m
