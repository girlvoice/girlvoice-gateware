#
# This file is part of LUNA.
#
# Copyright (c) 2020-2025 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

""" ULPI interfacing hardware. """

from amaranth              import *
from amaranth.lib          import wiring
from amaranth.lib.wiring   import In, Out

class Signature(wiring.Signature):
    """ULPI bus signature.

    Interface attributes
    --------------------
    i : :class:`Signal`
        Input value of the ULPI data lines.
    o : :class:`Signal`
        Output value of the ULPI data lines.
    oe : :class:`Signal`
        True iff we're trying to drive the ULPI data lines.
    clk : :class:`Signal`
        The ULPI clock signal.
    nxt : :class:`Signal`
        The ULPI 'next' throttle signal.
    stp : :class:`Signal`
        The ULPI 'stop' event signal.
    dir : :class:`Signal`
        The ULPI bus-direction signal.
    rst : :class:`Signal`
        The ULPI 'reset' signal.
    """

    def __init__(self):
        super().__init__({
            "data" : In(
                wiring.Signature({
                    "i"  :  In  (unsigned(8)),
                    "o"  :  Out (unsigned(8)),
                    "oe" :  Out (unsigned(1)),
                })
            ),
            # "clk" : Out (unsigned(1)),
            # "nxt" : In  (unsigned(1)),
            # "stp" : Out (unsigned(1)),
            # "dir" : In  (unsigned(1)),
            # "rst" : Out (unsigned(1)),

            # FIXME these are nested with i/o because luna is expecting Pins not the Signals that wiring provides
            "clk" : Out (wiring.Signature({ "o" : Out (unsigned(1)) })),
            "nxt" : In  (wiring.Signature({ "i" : In  (unsigned(1)) })),
            "stp" : Out (wiring.Signature({ "o" : Out (unsigned(1)) })),
            "dir" : In  (wiring.Signature({ "i" : In  (unsigned(1)) })),
            "rst" : Out (wiring.Signature({ "o" : Out (unsigned(1)) })),
        })
