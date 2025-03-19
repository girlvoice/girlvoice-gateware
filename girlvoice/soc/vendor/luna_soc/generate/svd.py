#
# This file is part of LUNA.
#
# Copyright (c) 2023-2025 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

"""Generate a SVD file for SoC designs."""

import logging
import sys

from collections            import defaultdict

from xml.dom                import minidom
from xml.etree              import ElementTree
from xml.etree.ElementTree  import Element, SubElement, Comment, tostring

from amaranth_soc           import csr
from amaranth_soc.memory    import MemoryMap, ResourceInfo

from ..gateware.cpu.ic      import InterruptMap
from .                      import introspect

class SVD:
    def __init__(self, memory_map: MemoryMap, interrupts: InterruptMap):
        self.interrupts      = interrupts
        self.csr_base        = introspect.csr_base(memory_map)
        self.csr_peripherals = introspect.csr_peripherals(memory_map)
        self.wb_peripherals  = introspect.wb_peripherals(memory_map)


    def generate(self, file=None, vendor="luna-soc", name="soc", description=None):
        device = self._device(vendor, name, description)

        # <peripherals />
        peripherals = SubElement(device, "peripherals")
        csr_base = self.csr_base
        logging.debug(f"\ncsr_base: 0x{csr_base:08x}")

        name         : MemoryMap.Name
        resource_info: ResourceInfo
        for name, resource_infos in self.csr_peripherals.items():
            # so, in theory, these are always sorted so:
            pstart = resource_infos[0].start
            pend   = resource_infos[-1].end

            name = "_".join([str(s) for s in name]) if isinstance(name, tuple) else name[0]
            logging.debug(f"  {name} 0x{pstart:04x} => 0x{pend:04x}  width: {pend - pstart} bytes")
            peripheral = self._peripheral(peripherals, name, pstart + csr_base, pend + csr_base)

            # <registers />
            registers = SubElement(peripheral, "registers")
            for resource_info in resource_infos:
                name = "_".join([str(s[0]) for s in resource_info.path[1:]])
                rstart = resource_info.start - pstart
                rend   = resource_info.end   - pstart
                access = resource_info.resource._access
                access = "read-only"  if type(access) is csr.FieldPort.Access.R else \
                         "write-only" if type(access) is csr.FieldPort.Access.W else \
                         "read-write"
                # TODO patch amaranth_soc/csr/reg.py:458 if not using vendored version
                description =  resource_info.resource.__class__.__doc__

                logging.debug(f"    {name}\t0x{rstart:02x} => 0x{rend:02x}  width: {rend - rstart} bytes")

                register = self._register(
                    registers,                     # root
                    name,                          # name
                    rstart,                        # register start
                    rend,                          # register end
                    access=access,                 # access
                    description=description        # description
                )

                # <fields />
                fields = SubElement(register, "fields")
                offset = 0
                for path, action in resource_info.resource:
                    name = "_".join([str(s) for s in path])
                    width = action.port.shape.width
                    access = "read-only"  if type(action) is csr.action.R else \
                             "write-only" if type(action) is csr.action.W else \
                             "read-write"
                    description = "" # TODO

                    bitRange = "[{:d}:{:d}]".format(offset + width - 1, offset)

                    logging.debug(f"      {name}\toffset:0x{offset} width: {width} bits range: {bitRange}")

                    field = self._field(
                        fields,                 # root
                        name,                   # name
                        offset,                 # field bitOffset
                        width,                  # field bitWidth
                        access=access,          # access
                        description=description # description
                    )

                    offset += width

        logging.debug("\nwishbone peripherals:")
        for name, t in self.wb_peripherals.items():
            logging.debug(f"\t{name} => {t}")

        logging.debug("\n---------------\n")

        # generate output
        output = ElementTree.tostring(device, 'utf-8')
        output = minidom.parseString(output)
        output = output.toprettyxml(indent="  ", encoding="utf-8")

        # write to file
        if file is None:
            sys.stdout.write(str(output.decode("utf-8")))
        else:
            file.write(str(output.decode("utf-8")))
            file.close()


    def _device(self, vendor, name, description):
        device = Element("device")

        device.set("schemaVersion", "1.1")
        device.set("xmlns:xs", "http://www.w3.org/2001/XMLSchema-instance")
        device.set("xs:noNamespaceSchemaLocation", "CMSIS-SVD.xsd")

        el = SubElement(device, "vendor")
        el.text = vendor
        el = SubElement(device, "name")
        el.text = name.upper()
        el = SubElement(device, "description")
        el.text = description or "TODO device.description"

        el = SubElement(device, "addressUnitBits")
        el.text = "8"          # TODO
        el = SubElement(device, "width")
        el.text = "32"         # TODO
        el = SubElement(device, "size")
        el.text = "32"         # TODO
        el = SubElement(device, "access")
        el.text = "read-write"
        el = SubElement(device, "resetValue")
        el.text = "0x00000000" # TODO
        el = SubElement(device, "resetMask")
        el.text = "0xFFFFFFFF" # TODO

        return device


    def _peripheral(self, root, name, start=0, end=0, groupName=None):
        peripheral = SubElement(root, "peripheral")

        el = SubElement(peripheral, "name")
        el.text = name
        el = SubElement(peripheral, "groupName")
        el.text = groupName or ""
        el = SubElement(peripheral, "baseAddress")
        el.text = "0x{:08x}".format(start)

        addressBlock = SubElement(peripheral, "addressBlock")
        el = SubElement(addressBlock, "offset")
        el.text = "0" # TODO
        el = SubElement(addressBlock, "size")     # TODO
        el.text = "0x{:02x}".format(end - start) # TODO
        el = SubElement(addressBlock, "usage")
        el.text = "registers"

        # interrupts
        # TODO search by start, end rather than name
        for v, (n, p) in self.interrupts.items():
            if name == n:
                interrupt = SubElement(peripheral, "interrupt")
                el = SubElement(interrupt, "name")
                el.text = n
                el = SubElement(interrupt, "value")
                el.text = str(v)
                break

        return peripheral

    def _register(self, root, name, start, end, access=None, description=None):
        register = SubElement(root, "register")

        el = SubElement(register, "name")
        el.text = name
        el = SubElement(register, "description")
        el.text = description or f"{name} register"

        el = SubElement(register, "addressOffset")
        el.text = "0x{:04x}".format(start)
        el = SubElement(register, "size")
        el.text = "{:d}".format((end - start) * 8) # TODO
        el = SubElement(register, "resetValue")
        el.text = "0x00" # TODO - calculate from fields ?

        if access is not None:
            el = SubElement(register, "access")
            el.text = access

        return register


    def _field(self, root, name, bitOffset, bitWidth, access=None, description=None):
        field =  SubElement(root, "field")

        el = SubElement(field, "name")
        el.text = name
        el = SubElement(field, "description")
        el.text = description or f"{name} field"

        el = SubElement(field, "bitOffset")
        el.text = "{:d}".format(bitOffset)
        el = SubElement(field, "bitWidth")
        el.text = "{:d}".format(bitWidth)
        el = SubElement(field, "bitRange")
        el.text = "[{:d}:{:d}]".format(bitOffset + bitWidth - 1, bitOffset)

        if access is not None:
            el = SubElement(field, "access")
            el.text = access

        return field


    def _vendorExtensions(self):
        pass
