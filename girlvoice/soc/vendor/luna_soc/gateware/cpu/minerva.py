#
# This file is part of LUNA.
#
# Copyright (c) 2023-2025 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

from amaranth import *
from amaranth.lib.wiring  import Component, In, Out, connect, flipped

try:
    from minerva.core import Minerva as MinervaCore
except:
    raise ImportError("To use Minerva with luna-soc you need to install it: pip install git+https://github.com/minerva-cpu/minerva")

from amaranth_soc         import wishbone
from amaranth_soc.periph  import ConstantMap

__all__ = ["Minerva"]

# - Minerva -------------------------------------------------------------------

class Minerva(Component):
    name       = "minerva"
    arch       = "riscv"
    byteorder  = "little"
    data_width = 32

    def __init__(self, **kwargs):
        super().__init__({
            "ext_reset":     In(unsigned(1)),
            "irq_external":  In(unsigned(32)),
            "ibus": Out(wishbone.Signature(
                addr_width=30,
                data_width=32,
                granularity=8,
                features=("err", "cti", "bte")
            )),
            "dbus": Out(wishbone.Signature(
                addr_width=30,
                data_width=32,
                granularity=8,
                features=("err", "cti", "bte")
            )),
        })

        self._cpu = MinervaCore(**kwargs)

    @property
    def reset_addr(self):
        return self._cpu._reset_address

    @property
    def muldiv(self):
        return "hard" if self._cpu.with_muldiv else "soft"

    def elaborate(self, platform):
        m = Module()

        m.submodules.minerva = self._cpu
        connect(m, self._cpu.ibus, flipped(self.ibus))
        connect(m, self._cpu.dbus, flipped(self.dbus))
        m.d.comb += [
            self._cpu.external_interrupt.eq(self.irq_external),
        ]

        return m
