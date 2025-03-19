#
# This file is part of LUNA.
#
# Copyright (c) 2023 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

"""Introspection tools for SoC designs."""

import logging

from collections          import defaultdict

from amaranth.lib         import wiring

from amaranth_soc         import csr
from amaranth_soc.memory  import MemoryMap, ResourceInfo

from ..gateware.cpu.ic    import InterruptMap


# - soc attributes ------------------------------------------------------------

def soc(fragment: wiring.Component) -> wiring.Component:
    if hasattr(fragment, "soc"):
        fragment = fragment.soc
    if not hasattr(fragment, "wb_decoder"):
        logging.warning("SoC designs need to have a 'wb_decoder' attribute.")
    if not hasattr(fragment, "interrupt_controller"):
        logging.warning("SoC designs need to have an 'interrupt_controller' attribute.")
    return fragment

def memory_map(fragment: wiring.Component) -> MemoryMap:
    return fragment.wb_decoder.bus.memory_map

def interrupts(fragment: wiring.Component) -> InterruptMap:
    return fragment.interrupt_controller.interrupts()

def reset_addr(fragment: wiring.Component) -> MemoryMap:
    return fragment.cpu.reset_addr


# - soc introspections --------------------------------------------------------

def csr_base(memory_map: MemoryMap) -> int:
    """Scan a memory map for the starting address for csr peripheral registers."""
    window: MemoryMap
    name:   MemoryMap.Name
    for window, name, (start, end, ratio) in memory_map.windows():
        if name[0] == "wb_to_csr":
            return start


def csr_peripherals(memory_map: MemoryMap) -> dict[MemoryMap.Name, list[ResourceInfo]]:
    """Scan a memory map for csr peripheral registers."""

    # group registers by peripheral
    csr_peripherals = defaultdict(list)

    # scan memory map for peripheral registers
    window: MemoryMap
    name:   MemoryMap.Name
    for window, name, (start, end, ratio) in memory_map.windows():
        resource_info: ResourceInfo
        for resource_info in window.all_resources():
            peripheral: MemoryMap.Name = resource_info.path[0]
            register:   csr.Register   = resource_info.resource
            if issubclass(register.__class__, csr.Register):
                csr_peripherals[peripheral].append(resource_info)

    return csr_peripherals


def wb_peripherals(memory_map: MemoryMap) -> dict[
        MemoryMap.Name,
        list[
            tuple[
                wiring.Component,
                MemoryMap.Name,
                (int, int)
            ]
        ]]:
    """Scan a memory map for wishbone peripherals."""

    # group by peripheral
    wb_peripherals = defaultdict(list)

    # scan memory map for wb peripherals
    window: MemoryMap
    for window, name, (start, end, ratio) in memory_map.windows():
        # window.resources() yields a tuple: `resource, resource_name, (start, end)`
        # where resource is the actual peripheral e.g. `core.blockram.Peripheral`
        for resource, path, (start, stop) in window.resources():
            wb_peripherals[name].append((resource, path, (start, stop)))

    return wb_peripherals
