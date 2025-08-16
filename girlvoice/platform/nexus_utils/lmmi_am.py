#!/usr/bin/env python3
from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
from amaranth.utils import exact_log2
from amaranth.sim import Simulator, SimulatorContext

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


class Register(wiring.Component):
    def __init__(self, data_width):
        super().__init__({"register": In(data_width)})

    def elaborate(self, platform):
        return Module()

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

        # range one greater than the sel width so we can
        cycle = Signal(range(len(wb_bus.sel) + 1))
        m.d.comb += lmmi_bus.offset.eq(Cat(cycle[:exact_log2(len(wb_bus.sel))], wb_bus.adr))

        with m.If(wb_bus.cyc & wb_bus.stb):
            # Amaranth magic
            with m.Switch(cycle):
                def segment(index):
                    return slice(index * wb_bus.granularity, (index + 1) * wb_bus.granularity)

                for index, sel_index in enumerate(wb_bus.sel):
                    with m.Case(index):
                        if index > 0:
                            # This might not actually work since lmmi expects
                            # to wait for the slave to give a valid signal
                            with m.If(wb_bus.sel[index-1] & lmmi_bus.rdata_valid):
                                m.d.sync += wb_bus.dat_r[segment(index - 1)].eq(lmmi_bus.rdata)
                        m.d.comb += lmmi_bus.wr_rdn.eq(sel_index & wb_bus.we)
                        m.d.comb += lmmi_bus.wdata.eq(wb_bus.dat_w[segment(index)])
                        m.d.comb += lmmi_bus.request.eq(sel_index)
                        m.d.sync += cycle.eq(cycle + 1)

                with m.Default():
                    with m.If(wb_bus.sel[index-1]):
                        m.d.sync += wb_bus.dat_r[segment(index)].eq(lmmi_bus.rdata)
                    m.d.sync += wb_bus.ack.eq(1)

        with m.If(wb_bus.ack):
            m.d.sync += cycle.eq(0)
            m.d.sync += wb_bus.ack.eq(0)

        return m


def main():
    clk_freq = 60e6

    dut = Module()
    map = MemoryMap(addr_width=8, data_width=8)
    lmmi = Interface(addr_width=8, data_width=8)
    lmmi.memory_map = map
    bridge = WishboneLMMIBridge(lmmi_bus=lmmi, data_width=32)

    # dut.submodules += lmmi
    dut.submodules += bridge

    async def tb(ctx: SimulatorContext):
        await ctx.tick()
        ctx.set(lmmi.ready, 1)
        ctx.set(bridge.wb_bus.cyc, 1)
        ctx.set(bridge.wb_bus.stb, 1)
        ctx.set(bridge.wb_bus.sel, 0x03)
        ctx.set(bridge.wb_bus.adr, 0x40000000)
        ctx.set(bridge.wb_bus.dat_w, 0xAB41)
        ctx.set(lmmi.rdata, 0xBC)
        for _ in range(len(bridge.wb_bus.sel) + 1):
            await ctx.tick()
        await ctx.tick()
        ctx.set(bridge.wb_bus.cyc, 0)
        ctx.set(bridge.wb_bus.sel, 0x01)
        ctx.set(bridge.wb_bus.stb, 0)
        await ctx.tick()
        await ctx.tick()
        ctx.set(bridge.wb_bus.cyc, 1)
        ctx.set(bridge.wb_bus.stb, 1)
        ctx.set(bridge.wb_bus.we, 1)
        ctx.set(bridge.wb_bus.sel, 0x03)
        ctx.set(bridge.wb_bus.adr, 0x40000000)
        ctx.set(bridge.wb_bus.dat_w, 0xAB41)
        for _ in range(len(bridge.wb_bus.sel) + 1):
            await ctx.tick()
        await ctx.tick()


    sim = Simulator(dut)
    sim.add_clock(1/clk_freq)
    sim.add_testbench(tb)
    with sim.write_vcd("lmmi_bridge.vcd"):
        sim.run()

if __name__ == "__main__":
    main()