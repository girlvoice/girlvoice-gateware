# Copyright (c) 2024 Seb Holzapfel <me@sebholzapfel.com>
#
# Based on some work from LUNA project licensed under BSD. Anything new
# in this file is issued under the following license:
#
# SPDX-License-Identifier: CERN-OHL-S-2.0

"""
Overview
--------

At a very high level, we have a vexriscv RISCV softcore running firmware (written
in Rust), that interfaces with a bunch of peripherals through CSR registers. As
the Vex also runs the menu system, often there is a dedicated peripheral with
CSRs used to tweak parameters of the DSP pipeline.

"""

import enum
import shutil
import subprocess
import os

from amaranth                                    import *
from amaranth.build                              import Attrs, Pins, PinsN, Platform, Resource, Subsignal
from amaranth.lib                                import wiring
from amaranth.lib.wiring                         import Component, In, Out, flipped, connect

from amaranth_soc                                import csr, gpio, wishbone
from amaranth_soc.csr.wishbone                   import WishboneCSRBridge
from amaranth_soc.wishbone.sram                  import WishboneSRAM

from .vendor.luna_soc.gateware.core               import spiflash, timer, uart
from .vendor.luna_soc.gateware.cpu                import InterruptController, VexRiscv
from .vendor.luna_soc.util                        import readbin
from .vendor.luna_soc.generate.svd                import SVD

from girlvoice.platform.nexus_utils.lram          import WishboneNXLRAM

kB = 1024
mB = 1024*kB

class GirlvoiceSoc(Component):
    def __init__(self, *, sys_clk_freq=60e6, finalize_csr_bridge=True,
                 mainram_size=128*kB,   cpu_variant="imac+dcache"):

        super().__init__({})

        self.sys_clk_freq = sys_clk_freq


        self.mainram_base         = 0x00000000
        self.mainram_size         = mainram_size
        self.spiflash_base        = 0x10000000
        self.spiflash_size        = 0x01000000 # 128Mbit / 16MiB
        self.csr_base             = 0xf0000000
        # offsets from csr_base
        self.spiflash_ctrl_base   = 0x00000100
        self.uart0_base           = 0x00000200
        self.timer0_base          = 0x00000300
        self.timer0_irq           = 0
        self.i2c0_base            = 0x00000400

        self.reset_addr  = self.mainram_base
        self.fw_base     = None

        # cpu
        self.cpu = VexRiscv(
            variant=cpu_variant,
            reset_addr=self.reset_addr,
        )

        # interrupt controller
        self.interrupt_controller = InterruptController(width=len(self.cpu.irq_external))

        # bus
        wb_data_width = 32
        self.wb_arbiter  = wishbone.Arbiter(
            addr_width=30,
            data_width=wb_data_width,
            granularity=8,
            features={"cti", "bte", "err"}
        )
        self.wb_decoder  = wishbone.Decoder(
            addr_width=30,
            data_width=wb_data_width,
            granularity=8,
            alignment=0,
            features={"cti", "bte", "err"}
        )

        # mainram
        self.mainram = WishboneNXLRAM(
            size=self.mainram_size,
            data_width=wb_data_width
        )
        self.wb_decoder.add(self.mainram.wb_bus, addr=self.mainram_base, name="mainram")

        # csr decoder
        self.csr_decoder = csr.Decoder(addr_width=28, data_width=8)

        # uart0
        uart_baud_rate = 115200
        divisor = int(self.sys_clk_freq // uart_baud_rate)
        self.uart0 = uart.Peripheral(divisor=divisor)
        self.csr_decoder.add(self.uart0.bus, addr=self.uart0_base, name="uart0")

        # FIXME: timer events / isrs currently not implemented, adding the event
        # bus to the csr decoder segfaults yosys somehow ...

        # timer0
        self.timer0 = timer.Peripheral(width=32)
        self.csr_decoder.add(self.timer0.bus, addr=self.timer0_base, name="timer0")
        self.interrupt_controller.add(self.timer0, number=self.timer0_irq, name="timer0")

        # spiflash peripheral
        # self.spi0_phy        = spiflash.SPIPHYController(domain="sync", divisor=0)
        # self.spiflash_periph = spiflash.Peripheral(phy=self.spi0_phy, mmap_size=self.spiflash_size,
        #                                            mmap_name="spiflash")
        # self.wb_decoder.add(self.spiflash_periph.bus, addr=self.spiflash_base, name="spiflash")
        # self.csr_decoder.add(self.spiflash_periph.csr, addr=self.spiflash_ctrl_base, name="spiflash_ctrl")


        # mobo i2c
        # self.i2c0 = i2c.Peripheral()
        # self.i2c_stream0 = i2c.I2CStreamer(period_cyc=256)
        # self.csr_decoder.add(self.i2c0.bus, addr=self.i2c0_base, name="i2c0")

        self.permit_bus_traffic = Signal()

        self.extra_rust_constants = []

        if finalize_csr_bridge:
            self.finalize_csr_bridge()

    def finalize_csr_bridge(self):

        # Finalizing the CSR bridge / peripheral memory map may not be desirable in __init__
        # if we want to add more after this class has been instantiated. So it's optional
        # during __init__ but MUST be called once before the design is elaborated.

        self.wb_to_csr = WishboneCSRBridge(self.csr_decoder.bus, data_width=32)
        self.wb_decoder.add(self.wb_to_csr.wb_bus, addr=self.csr_base, sparse=False, name="wb_to_csr")

    def add_rust_constant(self, line):
        self.extra_rust_constants.append(line)

    def elaborate(self, platform):

        m = Module()

        # bus
        m.submodules.wb_arbiter = self.wb_arbiter
        m.submodules.wb_decoder = self.wb_decoder
        wiring.connect(m, self.wb_arbiter.bus, self.wb_decoder.bus)

        # cpu
        m.submodules.cpu = self.cpu
        self.wb_arbiter.add(self.cpu.ibus)
        self.wb_arbiter.add(self.cpu.dbus)

        # interrupt controller
        m.submodules.interrupt_controller = self.interrupt_controller
        # TODO wiring.connect(m, self.cpu.irq_external, self.irqs.pending)
        m.d.comb += self.cpu.irq_external.eq(self.interrupt_controller.pending)

        # mainram
        m.submodules.mainram = self.mainram

        # csr decoder
        m.submodules.csr_decoder = self.csr_decoder

        # uart0
        m.submodules.uart0 = self.uart0
        uart = platform.request("uart")
        m.d.comb += self.uart0.pins.rx.eq(uart.rx.i)
        m.d.comb += uart.tx.o.eq(self.uart0.pins.tx.o)
        # if sim.is_hw(platform):
        #     uart0_provider = uart.Provider(0)
        #     m.submodules.uart0_provider = uart0_provider
        #     wiring.connect(m, self.uart0.pins, uart0_provider.pins)

        # timer0
        m.submodules.timer0 = self.timer0

        # i2c0
        # m.submodules.i2c0 = self.i2c0
        # m.submodules.i2c_stream0 = self.i2c_stream0
        # wiring.connect(m, self.i2c0.i2c_stream, self.i2c_stream0.control)
        # if sim.is_hw(platform):
        #     i2c0_provider = i2c.Provider()
        #     m.submodules.i2c0_provider = i2c0_provider
        #     wiring.connect(m, self.i2c_stream0.pins, i2c0_provider.pins)

        # spiflash
        # m.submodules.spi0_phy = self.spi0_phy
        # m.submodules.spiflash_periph = self.spiflash_periph

        # wiring.connect(m, self.i2c1.i2c_stream, self.pmod0.i2c_master.i2c_override)

        # if sim.is_hw(platform):

        #     # generate our domain clocks/resets
        #     m.submodules.car = car = platform.clock_domain_generator(self.clock_settings)


        #     # Connect encoder button to RebootProvider
        #     m.submodules.reboot = reboot = RebootProvider(self.clock_settings.frequencies.sync)
        #     m.d.comb += reboot.button.eq(self.encoder0._button.f.button.r_data)
        # else:
        #     m.submodules.car = sim.FakeTiliquaDomainGenerator()

        # wishbone csr bridge
        m.submodules.wb_to_csr = self.wb_to_csr

        # Memory controller hangs if we start making requests to it straight away.
        on_delay = Signal(32)
        with m.If(on_delay < 0xFF):
            m.d.comb += self.cpu.ext_reset.eq(1)
        with m.If(on_delay < 0xFFFF):
            m.d.sync += on_delay.eq(on_delay+1)
        with m.Else():
            m.d.sync += self.permit_bus_traffic.eq(1)

        return m

    def gensvd(self, dst_svd):
        """Generate top-level SVD."""
        print("Generating SVD ...", dst_svd)
        with open(dst_svd, "w") as f:
            SVD(self).generate(file=f)
        print("Wrote SVD ...", dst_svd)

    def genmem(self, dst_mem):
        """Generate linker regions for Rust (memory.x)."""
        print("Generating (rust) memory.x ...", dst_mem)
        # .text, .rodata in shared block RAM region
        memory_x = (
            "MEMORY {{\n"
            "    mainram : ORIGIN = {mainram_base}, LENGTH = {mainram_size}\n"
            "}}\n"
            "REGION_ALIAS(\"REGION_TEXT\", mainram);\n"
            "REGION_ALIAS(\"REGION_RODATA\", mainram);\n"
            "REGION_ALIAS(\"REGION_DATA\", mainram);\n"
            "REGION_ALIAS(\"REGION_BSS\", mainram);\n"
            "REGION_ALIAS(\"REGION_HEAP\", mainram);\n"
            "REGION_ALIAS(\"REGION_STACK\", mainram);\n"
        )
        with open(dst_mem, "w") as f:
            f.write(memory_x.format(mainram_base=hex(self.mainram_base),
                                    mainram_size=hex(self.mainram.size),
                                    ))

    def genconst(self, dst):
        """Generate some high-level constants used by application code."""
        # TODO: better to move these to SVD vendor section?
        print("Generating (rust) constants ...", dst)
        with open(dst, "w") as f:
            f.write(f"pub const UI_NAME: &str            = \"{self.ui_name}\";\n")
            f.write(f"pub const UI_SHA: &str             = \"{self.ui_sha}\";\n")
            f.write(f"pub const HW_REV_MAJOR: u32        = {self.platform_class.version_major};\n")
            f.write(f"pub const CLOCK_SYNC_HZ: u32       = {self.clock_settings.frequencies.sync};\n")
            f.write(f"pub const CLOCK_FAST_HZ: u32       = {self.clock_settings.frequencies.fast};\n")
            f.write(f"pub const CLOCK_DVI_HZ: u32        = {self.clock_settings.frequencies.dvi};\n")
            f.write(f"pub const CLOCK_AUDIO_HZ: u32      = {self.clock_settings.frequencies.audio};\n")
            f.write(f"pub const PSRAM_BASE: usize        = 0x{self.psram_base:x};\n")
            f.write(f"pub const PSRAM_SZ_BYTES: usize    = 0x{self.psram_size:x};\n")
            f.write(f"pub const PSRAM_SZ_WORDS: usize    = PSRAM_SZ_BYTES / 4;\n")
            f.write(f"pub const SPIFLASH_BASE: usize     = 0x{self.spiflash_base:x};\n")
            f.write(f"pub const SPIFLASH_SZ_BYTES: usize = 0x{self.spiflash_size:x};\n")
            f.write(f"pub const H_ACTIVE: u32            = {self.video.fb_hsize};\n")
            f.write(f"pub const V_ACTIVE: u32            = {self.video.fb_vsize};\n")
            f.write(f"pub const VIDEO_ROTATE_90: bool    = {'true' if self.video_rotate_90 else 'false'};\n")
            f.write(f"pub const PSRAM_FB_BASE: usize     = 0x{self.video.fb_base:x};\n")
            f.write(f"pub const PX_HUE_MAX: i32          = 16;\n")
            f.write(f"pub const PX_INTENSITY_MAX: i32    = 16;\n")
            f.write(f"pub const N_BITSTREAMS: usize      = 8;\n")
            f.write(f"pub const MANIFEST_BASE: usize     = SPIFLASH_BASE + SPIFLASH_SZ_BYTES - 4096;\n")
            f.write(f"pub const MANIFEST_SZ_BYTES: usize = 4096;\n")
            f.write("// Extra constants specified by an SoC subclass:\n")
            for l in self.extra_rust_constants:
                f.write(l)

    def regenerate_pac_from_svd(svd_path):
        """
        Generate Rust PAC from an SVD.
        Currently all SoC reuse the same `pac_dir`, however this
        should become local to each SoC at some point.
        """
        pac_dir = "src/rs/pac"
        pac_build_dir = os.path.join(pac_dir, "build")
        pac_gen_dir   = os.path.join(pac_dir, "src/generated")
        src_genrs     = os.path.join(pac_dir, "src/generated.rs")
        shutil.rmtree(pac_build_dir, ignore_errors=True)
        shutil.rmtree(pac_gen_dir, ignore_errors=True)
        os.makedirs(pac_build_dir)
        if os.path.isfile(src_genrs):
            os.remove(src_genrs)

        subprocess.check_call([
            "svd2rust",
            "-i", svd_path,
            "-o", pac_build_dir,
            "--target", "riscv",
            "--make_mod",
            "--ident-formats-theme", "legacy"
            ], env=os.environ)

        shutil.move(os.path.join(pac_build_dir, "mod.rs"), src_genrs)
        shutil.move(os.path.join(pac_build_dir, "device.x"),
                    os.path.join(pac_dir,       "device.x"))

        subprocess.check_call([
            "form",
            "-i", src_genrs,
            "-o", pac_gen_dir,
            ], env=os.environ)

        shutil.move(os.path.join(pac_gen_dir, "lib.rs"), src_genrs)

        subprocess.check_call([
            "cargo", "fmt", "--", "--emit", "files"
            ], env=os.environ, cwd=pac_dir)

        print("Rust PAC updated at ...", pac_dir)

    def compile_firmware(rust_fw_root, rust_fw_bin):
        subprocess.check_call([
            "cargo", "build", "--release"
            ], env=os.environ, cwd=rust_fw_root)
        subprocess.check_call([
            "cargo", "objcopy", "--release", "--", "-Obinary", rust_fw_bin
            ], env=os.environ, cwd=rust_fw_root)