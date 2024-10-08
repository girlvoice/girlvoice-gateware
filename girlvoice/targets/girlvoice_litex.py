#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2020 David Corrigan <davidcorrigan714@gmail.com>
# Copyright (c) 2020 Alan Green <avg@google.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer

from litex.gen import *

from girlvoice.platform.litex import girlvoice_rev_a

from litex.soc.cores.ram import NXLRAM
from litex.soc.cores.clock import NXPLL
from litex.soc.cores.gpio import GPIOOut
from litex.build.io import CRG
from litex.build.generic_platform import *

from litex.soc.cores.clock import *
from litex.soc.integration.soc_core import *
from litex.soc.integration.soc import SoCRegion, SoCIORegion
from litex.soc.integration.builder import *
from litex.soc.cores.bitbang import I2CMaster

from girlvoice.io.nexus_i2c import NexusI2CMaster

kB = 1024
mB = 1024*kB

def add_radiant_constraints(platform):
    platform.add_platform_command("ldc_set_sysconfig {{CONFIGIO_VOLTAGE_BANK0=3.3 CONFIGIO_VOLTAGE_BANK1=3.3 JTAG_PORT=DISABLE MASTER_SPI_PORT=SERIAL}}")
    platform.add_platform_command("ldc_set_location -site {{PLL_LRC}} [ get_cells {{PLL_0.PLL_inst}} ]")
    platform.add_platform_command("ldc_set_vcc -bank 0 3.3")
    platform.add_platform_command("ldc_set_vcc -bank 1 3.3")
    platform.add_platform_command("ldc_set_vcc -bank 3 1.8")
    platform.add_platform_command("ldc_set_vcc -bank 5 1.8")


class _PowerManagement(LiteXModule):
    def __init__(self, platform):
        ## Power On/Off
        pwr_button = platform.request("btn_pwr")
        pwr_en = platform.request("pwr_en")

        pwr_on = Signal(reset=1)
        self.comb += pwr_en.eq(pwr_on)

        btn_last = Signal(reset=1)
        btn_rising = Signal()
        self.sync += btn_last.eq(pwr_button)
        self.sync += btn_rising.eq(pwr_button & ~btn_last)

        fsm = FSM(reset_state="PWR_ON")
        self.sync += [
            If(btn_rising,
                pwr_on.eq(0)
            )
        ]
# CRG ----------------------------------------------------------------------------------------------

class _CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq):
        self.rst    = Signal()
        self.cd_por = ClockDomain()
        self.cd_sys = ClockDomain()

        # Built in OSC
        self.hf_clk = NXOSCA()
        hf_clk_freq = 25e6
        self.hf_clk.create_hf_clk(self.cd_por, hf_clk_freq)
        # self.cd_por.clk = platform.request("clk12")

        # Power on reset
        por_count = Signal(16, reset=2**16-1)
        por_done  = Signal()
        self.comb += por_done.eq(por_count == 0)
        self.sync.por += If(~por_done, por_count.eq(por_count - 1))

        self.rst_n = platform.request("btn_down")
        # self.specials += AsyncResetSynchronizer(self.cd_por, ~self.rst_n)

        # PLL
        self.sys_pll = sys_pll = NXPLL(platform=platform, create_output_port_clocks=True)
        self.comb += sys_pll.reset.eq(self.rst)
        sys_pll.register_clkin(self.cd_por.clk, hf_clk_freq)
        sys_pll.create_clkout(self.cd_sys, sys_clk_freq)
        self.specials += AsyncResetSynchronizer(self.cd_sys, ~self.sys_pll.locked | ~por_done )

        self.platform = platform

    # We have to add this platform command here to ensure that it comes after the PLL clock port has been created
    def do_finalize(self):
        if self.platform.toolchain == "radiant":
            self.platform.add_platform_command("set_clock_groups -asynchronous -group [get_clocks crg_clkout] -group [get_clocks PLL_0_P]")


# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    mem_map = {
        "rom"      : 0x00000000,
        "sram"     : 0x40000000,
        "main_ram" : 0x60000000,
        "csr"      : 0xf0000000,
        "lmmi"     : 0x81000000,
    }

    def __init__(self, sys_clk_freq=60e6, device="LIFCL-17-8SG72C", toolchain="oxide",
        with_spi_flash  = False,
        **kwargs):
        platform = girlvoice_rev_a.Platform(device=device, toolchain=toolchain)

        if toolchain == "radiant":
            add_radiant_constraints(platform)

        # CRG --------------------------------------------------------------------------------------
        self.crg = _CRG(platform, sys_clk_freq)


        # SoCCore -----------------------------------------_----------------------------------------
        # Disable Integrated SRAM since we want to instantiate LRAM specifically for it
        kwargs["integrated_sram_size"] = 0
        # Make serial_pmods available
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on girlvoice rev A :3", **kwargs)

        # 128KB LRAM (used as SRAM) ---------------------------------------------------------------
        self.spram = NXLRAM(32, 64*kB)
        self.bus.add_slave("sram", self.spram.bus, SoCRegion(origin=self.mem_map["sram"], size=16*kB))

        self.main_ram = NXLRAM(32, 64*kB)
        self.bus.add_slave("main_ram", self.main_ram.bus, SoCRegion(origin=self.mem_map["main_ram"], size=64*kB))

        led = platform.request("led")

        self.comb += led.eq(self.crg.rst_n)

        self.power_manager = _PowerManagement(platform)

        # I2C Hard IP --------------------------------------------------------------------

        pads = platform.request("i2c")
        self.i2c = NexusI2CMaster(pads=pads, sys_clk_freq=sys_clk_freq, scl_freq=400e3)
        self.bus.add_slave("lmmi", self.i2c.bus.wishbone, SoCRegion(origin=self.mem_map["lmmi"], size=kB, cached=False))
        platform.add_period_constraint(self.i2c.alt_scl_oen, period=1e9/400e6)

        clk12 = platform.request("clk12")
        clk12_freq = 12e6
        self.cd_clk12 = ClockDomain()
        self.comb += self.cd_clk12.clk.eq(clk12)

        amp = platform.request("amp")
        self.comb += amp.en.eq(1)

        tp_rstn = platform.request("tp_rstn")
        self.comb += tp_rstn.eq(1)

        aux_mclk = platform.request("aux_mclk")
        self.comb += aux_mclk.eq(clk12)

        bclk_freq = 3072e3
        clk_ratio = int(clk12_freq // bclk_freq)
        clk_div = Signal(max=clk_ratio)

        bclk = Signal()
        self.sync.clk12 += [
            If(clk_div >= (clk_ratio - 1) // 2,
                clk_div.eq(0),
                bclk.eq(~bclk),
            ).Else(
                clk_div.eq(clk_div + 1)
            )
        ]

        self.comb += amp.bclk.eq(bclk)


        wclk = Signal()

        bclk_negedge = Signal()
        bclk_last = Signal()
        self.sync += bclk_last.eq(bclk)
        self.comb += bclk_negedge.eq(~bclk & bclk_last)

        count = Signal(max=32)
        self.sync += [
            If(bclk_negedge,
                count.eq(count + 1)
            ),
            If(count == 0,
                wclk.eq(~wclk)
            )
        ]

        self.comb += amp.wclk.eq(wclk)
        # SPI Flash --------------------------------------------------------------------------------
        # if with_spi_flash:
        #     from litespi.modules import MX25L12833F
        #     from litespi.opcodes import SpiNorFlashOpCodes as Codes
        #     self.add_spi_flash(mode="4x", clk_freq=100_000, module=MX25L12833F(Codes.READ_4_4_4), with_master=True)



# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    parser = LiteXArgumentParser(platform=girlvoice_rev_a.Platform, description="LiteX SoC on Crosslink-NX Eval Board.")
    parser.add_target_argument("--device",        default="LIFCL-17-8SG72C", help="FPGA device.")
    parser.add_target_argument("--sys-clk-freq",  default=60e6, type=float,   help="System clock frequency.")
    parser.add_target_argument("--serial",        default="serial",           help="UART Pins")
    parser.add_target_argument("--programmer",    default="iceprog",          help="Programmer (radiant or iceprog).")
    parser.add_target_argument("--address",       default=0x0,                help="Flash address to program bitstream at.")
    parser.add_target_argument("--prog-target",   default="flash",           help="Programming Target (direct or flash).")
    # parser.add_target_argument("--with-spi-flash", action="store_true",       help="Enable SPI Flash (MMAPed).")
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq = args.sys_clk_freq,
        device       = args.device,
        toolchain    = args.toolchain,
        # with_spi_flash = args.with_spi_flash,
        **parser.soc_argdict
    )
    builder = Builder(soc, **parser.builder_argdict)
    if args.build:
        if args.toolchain == "radiant":
            builder.build(**parser.toolchain_argdict)
        builder.build(**parser.toolchain_argdict)

    if args.load:
        prog = soc.platform.create_programmer(args.prog_target, args.programmer)
        if args.programmer == "iceprog" and args.prog_target == "flash":
            prog.flash(args.address, builder.get_bitstream_filename(mode="sram"))
        else:
            prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

if __name__ == "__main__":
    main()
