from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.utils import exact_log2

from amaranth_soc import wishbone
from amaranth_soc.memory import MemoryMap

from girlvoice.platform.nexus_utils import lmmi


class Signature(wiring.Signature):
    def __init__(self, addr_width, data_width):
        self._addr_width = addr_width
        self._data_width = data_width
        members = {
            "offset": Out(addr_width),
            "rdata": In(data_width),
            "wdata": Out(data_width),
            "wr_rdn": Out(1),
            "request": Out(1),
            "ready": In(1),
            "rdata_valid": In(1)
        }

        super().__init__(members=members)

    @property
    def addr_width(self):
        return self._addr_width

    @property
    def data_width(self):
        return self._data_width

    def create(self, *, path=None, src_loc_at=0):
        """Create a compatible interface.

        See :meth:`wiring.Signature.create` for details.

        Returns
        -------
        An :class:`Interface` object using this signature.
        """
        return Interface(addr_width=self.addr_width, data_width=self.data_width,
                         path=path, src_loc_at=1 + src_loc_at)

class Interface(wiring.PureInterface):
    signature: Signature
    def __init__(self, addr_width, data_width, path=None, src_loc_at=0):
        super().__init__(Signature(addr_width=addr_width, data_width=data_width), path=path, src_loc_at=1 + src_loc_at)
        self._memory_map = None

    @property
    def addr_width(self):
        return self.signature.addr_width

    @property
    def data_width(self):
        return self.signature.data_width

    @property
    def memory_map(self):
        if self._memory_map is None:
            raise AttributeError(f"{self!r} does not have a memory map")
        return self._memory_map

    @memory_map.setter
    def memory_map(self, memory_map: MemoryMap):
        if not isinstance(memory_map, MemoryMap):
            raise TypeError(f"Memory map must be an instance of MemoryMap, not {memory_map!r}")
        if memory_map.addr_width != self.addr_width:
            raise ValueError(f"Memory map has address width {memory_map.addr_width}, which is not "
                             f"the same as bus interface address width {self.addr_width}")
        if memory_map.data_width != self.data_width:
            raise ValueError(f"Memory map has data width {memory_map.data_width}, which is not the "
                             f"same as bus interface data width {self.data_width}")
        self._memory_map = memory_map

'''
Really basic converter to bridge LMMI to Wishbone
'''
class WishboneLMMIBridge(wiring.Component):
    def __init__(self, lmmi_bus: Interface , data_width=None, name=None):
        if isinstance(lmmi_bus, wiring.FlippedInterface):
            lmmi_bus_unflipped = wiring.flipped(lmmi_bus)
        else:
            lmmi_bus_unflipped = lmmi_bus

        if not isinstance(lmmi_bus_unflipped, Interface):
            raise TypeError(f"LMMI bus must be an instance of lmmi.Interface, not "
                            f"{lmmi_bus_unflipped!r}")
        if data_width is None:
            data_width = lmmi_bus.data_width

        ratio  = data_width // lmmi_bus.data_width
        wb_sig = wishbone.Signature(
            addr_width=max(0, lmmi_bus.addr_width - exact_log2(ratio)),
            data_width=data_width,
            granularity=lmmi_bus.data_width
        )
        super().__init__({"wb_bus": In(wb_sig)})

        self.wb_bus.memory_map = MemoryMap(addr_width=lmmi_bus.addr_width, data_width=lmmi_bus.data_width)

        self.wb_bus.memory_map.add_window(lmmi_bus.memory_map, name=name)
        self._lmmi_bus = lmmi_bus

    @property
    def lmmi_bus(self):
        return self._lmmi_bus

    def elaborate(self, platform):
        m = Module()
        lmmi_bus = self.lmmi_bus
        wb_bus = self.wb_bus

        with m.FSM():
            with m.State("IDLE"):
                with m.If(wb_bus.cyc & wb_bus.stb):
                    m.d.comb += [
                        lmmi_bus.wdata.eq(wb_bus.dat_w),
                        lmmi_bus.request.eq(1),
                        lmmi_bus.wr_rdn.eq(wb_bus.we),
                        lmmi_bus.offset.eq(wb_bus.adr[4:])
                    ]
                    with m.If(wb_bus.we):
                        with m.If(lmmi_bus.ready):
                            m.d.comb += wb_bus.ack.eq(1)
                            m.next = "WRITE_WAIT"
                    with m.Else():
                        m.next = "READ_WAIT"
            with m.State("WRITE_WAIT"):
                m.d.comb += wb_bus.ack.eq(1)
                m.next = "IDLE"
            with m.State("READ_WAIT"):
                with m.If(lmmi_bus.rdata_valid):
                    m.d.comb += {
                        wb_bus.dat_r.eq(lmmi_bus.rdata),
                        wb_bus.ack.eq(1)
                    }
                    m.next += "IDLE"
        return m