#
# This file is part of LUNA.
#
# Copyright (c) 2020-2025 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

""" The simplest interrupt controller. """

from amaranth              import *
from amaranth.lib          import wiring
from amaranth.lib.wiring   import In, Out

# type aliases only in py 3.12 :-(
# type InterruptMap = dict[int, (str, wiring.Component)]
InterruptMap = dict[int, (str, wiring.Component)]

class InterruptController(wiring.Component):
    def __init__(self, *, width):
        super().__init__({
            "pending":  Out(unsigned(width)),
        })

        self._interrupts: InterruptMap = dict()

    def interrupts(self) -> InterruptMap:
        return self._interrupts

    def add(self, peripheral, *, name, number=None):
        if number is None:
            raise ValueError("You need to supply a value for the IRQ number.")
        if number in self._interrupts.keys():
            raise ValueError(f"IRQ number '{number}' has already been used.")
        if name in dict(self._interrupts.values()).keys():
            raise ValueError(f"Peripheral name '{name}' has already been used.")
        if peripheral in dict(self._interrupts.values()).values():
            raise ValueError(f"Peripheral '{name}' has already been added: {peripheral}")
        self._interrupts[number] = (name, peripheral)

    def elaborate(self, platform):
        m = Module()

        for number, (name, peripheral) in self._interrupts.items():
            m.d.comb += self.pending[number].eq(peripheral.irq)

        return m
