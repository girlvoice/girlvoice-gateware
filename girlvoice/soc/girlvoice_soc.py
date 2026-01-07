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
in Rust), that interfaces with a bunch of peripherals through CSR registers.
  ┌─────────────────────────┐                     ┌──────────────────────────┐
  │                         │  32-bit Wishbone    │                          │
  │                         │       ┌────────────►│  Vocoder                 │
  │                         │       │             │  CS Registers            │
  │                         │       │             │                          │
  │         VexRiscv        │◄──────┤             │                          │
  │                         │       │             └──────────────────────────┘
  │                         │       │
  │                         │       │             ┌──────────────────────────┐
  │                         │       │             │                          │
  └─────────────────────────┘       ├────────────►│  SPI Controller          │
  ┌─────────────────────────┐       │             │                          │
  │                         │       │             └──────────────────────────┘
  │   Wishbone-attached     │       │
  │   SRAM                  │◄──────┤             ┌──────────────────────────┐
  │                         │       │             │ Timer                    │
  │                         │       ├────────────►│                          │
  └─────────────────────────┘       │             └──────────────────────────┘
  ┌─────────────────────────┐       │
  │                         │       │
  │                         │       │
  │   Lattice I2C FIFO IP   │◄──────┘
  │                         │
  │                         │
  └─────────────────────────┘
"""

import shutil
import subprocess
import os

from amaranth                                    import *
from amaranth.build                              import Platform
from amaranth.lib                                import wiring
from amaranth.lib.wiring                         import Component, In, Out, flipped, connect

from amaranth_soc                                import csr, gpio, wishbone
from amaranth_soc.csr.wishbone                   import WishboneCSRBridge
from amaranth_soc.wishbone.sram                  import WishboneSRAM

from luna_soc.gateware.core               import spiflash, timer, uart
from luna_soc.gateware.cpu                import InterruptController, VexRiscv
from luna_soc.util                        import readbin
from luna_soc.generate.svd                import SVD
from numpy import add

from girlvoice.dsp import vocoder
import girlvoice.platform.nexus_utils.lmmi as lmmi
from girlvoice.platform.nexus_utils.lram          import WishboneNXLRAM
from girlvoice.soc.provider import girlvoice_rev_a as provider

from girlvoice.dsp.vocoder import StaticVocoder, ThreadedVocoderChannel
from girlvoice.io.i2s import i2s_rx, i2s_tx
from girlvoice.io import spi
from girlvoice.platform.nexus_utils.i2c_fifo import I2CFIFO

kB = 1024
mB = 1024*kB

class GirlvoiceSoc(Component):
    def __init__(self, *, sys_clk_freq=60e6, finalize_csr_bridge=True,
                 mainram_size=256*kB, cpu_variant="imac+dcache", use_spi_flash = False, sim = False):

        super().__init__({})

        self.firmware_path = ""
        self.sim = sim

        self.sys_clk_freq = sys_clk_freq

        self.use_spi_flash        = False
        self.mainram_base         = 0x00000000
        self.mainram_size         = mainram_size
        self.spiflash_base        = 0x10000000
        self.spiflash_size        = 0x00400000 # 32Mbit / 4MiB
        self.csr_base             = 0xf0000000
        self.lmmi_base            = 0xa0000000
        self.wavetable_base       = 0xb0000000

        self.spi_data_base        = 0xc0000000
        # offsets from csr_base
        self.spiflash_ctrl_base   = 0x00000100
        self.uart0_base           = 0x00000200
        self.timer0_base          = 0x00000300
        self.timer0_irq           = 0
        self.i2c0_base            = 0x00000400
        self.led0_base            = 0x00000500
        self.gpo1_base            = 0x00000600

        if not use_spi_flash:
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
        self.wb_arbiter = wishbone.Arbiter(
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
        if not self.sim:
            self.mainram = WishboneNXLRAM(
                size=self.mainram_size,
                data_width=wb_data_width,
            )
        else:
            self.mainram = WishboneSRAM(
                size=mainram_size,
                data_width=wb_data_width,
                granularity=8
            )
        self.wb_decoder.add(self.mainram.wb_bus, addr=self.mainram_base, name="blockram")


        # csr decoder

        if not self.sim:
            csr_addr_width = 28
            csr_data_width = 8
            self.csr_decoder = csr.Decoder(addr_width=csr_addr_width, data_width=csr_data_width)

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

            # led
            self.led0 = gpio.Peripheral(pin_count=1, addr_width=4, data_width=8)
            self.csr_decoder.add(self.led0.bus, addr=self.led0_base, name="led0")

            self.gpo_1 = gpio.Peripheral(pin_count=2, addr_width=4, data_width=8)
            self.csr_decoder.add(self.gpo_1.bus, addr=self.gpo1_base, name="gpo1")

            # LCD SPI control
            self.spi_pads = provider.SPIFlashProvider(id="spi")
            self.spi0_phy        = spiflash.SPIPHYController(
                pads = self.spi_pads.pins,
                domain="fast",
                divisor=1
            )
            self.spi0            = spi.SPIController(name="spi_ctrl")

            self.csr_decoder.add(self.spi0.bus, addr=self.spiflash_ctrl_base, name="spiflash_ctrl")
            self.wb_decoder.add(self.spi0.wb_bus, addr=self.spi_data_base, name="spi_fifo")

        # lattice i2c
        self.i2c = I2CFIFO(scl_freq=400e3, use_hard_io=True, sim=sim)
        self.lmmi_to_wb = lmmi.WishboneLMMIBridge(lmmi_bus = self.i2c.lmmi, data_width=32)
        self.wb_decoder.add(self.lmmi_to_wb.wb_bus, addr=self.lmmi_base, name = "wb_to_lmmi")

        sample_width = 16

        bclk_freq = 4e6
        fs = 32e3

        self.i2s_tx = i2s_tx(self.sys_clk_freq, sclk_freq=bclk_freq, sample_width=sample_width)
        self.i2s_rx = i2s_rx(self.sys_clk_freq, sclk_freq=bclk_freq, sample_width=sample_width)

        # Vocoder!

        self.vocoder = StaticVocoder(
            start_freq=100,
            end_freq=5000,
            num_channels=14,
            clk_sync_freq=sys_clk_freq,
            fs=fs,
            sample_width=sample_width,
            channel_class=ThreadedVocoderChannel
        )

        # Add vocoder wavetable to wb bus
        self.wb_decoder.add(self.vocoder.synth.wb_bus, addr=self.wavetable_base, name="wavetable")

        self.permit_bus_traffic = Signal()

        self.extra_rust_constants = []

        if finalize_csr_bridge and not self.sim:
            self.finalize_csr_bridge()

    def finalize_csr_bridge(self):

        # Finalizing the CSR bridge / peripheral memory map may not be desirable in __init__
        # if we want to add more after this class has been instantiated. So it's optional
        # during __init__ but MUST be called once before the design is elaborated.

        self.wb_to_csr = WishboneCSRBridge(self.csr_decoder.bus, data_width=32)
        self.wb_decoder.add(self.wb_to_csr.wb_bus, addr=self.csr_base, sparse=False, name="wb_to_csr")

    def add_rust_constant(self, line: str):
        self.extra_rust_constants.append(line)

    def elaborate(self, platform: Platform):

        m = Module()

        # mainram
        maybe_fw_init = readbin.get_mem_data(self.firmware_path, data_width=32, endianness="little")
        if maybe_fw_init is None:
            raise RuntimeError("No firmware found to initialize")
        if not self.use_spi_flash:
            print("Initializing SoC RAM from firmware")
            self.mainram.init = maybe_fw_init

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
        if not self.sim:
            m.submodules.csr_decoder = self.csr_decoder

        # uart0
        if not self.sim:
            m.submodules.uart0 = self.uart0
            uart = platform.request("uart")
            m.d.comb += self.uart0.pins.rx.eq(uart.rx.i)
            m.d.comb += uart.tx.o.eq(self.uart0.pins.tx.o)

            # timer0
            m.submodules.timer0 = self.timer0

            # led0
            m.submodules.led0 = self.led0
            led_io = platform.request("led")
            m.d.comb += led_io.o.eq(self.led0.pins[0].o)

            m.submodules.gpo1 = self.gpo_1
            dc_pin = platform.request("dc")
            bl_pin = platform.request("bl")

            m.d.comb += dc_pin.o.eq(self.gpo_1.pins[0].o)
            m.d.comb += bl_pin.o.eq(self.gpo_1.pins[1].o)

        # i2c0
        m.submodules.i2c0 = self.i2c
        m.submodules.wb_to_lmmi = self.lmmi_to_wb


        # Multiboot module is required to unlock use of
        # SPI pins for the LCD
        m.submodules.multiboot = Instance(
            "MULTIBOOT",
            p_SOURCESEL="EN",
            i_AUTOREBOOT=0,
            i_MSPIMADDR=0
        )

        # lcd spi controller
        m.submodules.spi0_phy = self.spi0_phy
        m.submodules.spi0 = self.spi0
        m.submodules.spi_provider = self.spi_pads

        wiring.connect(m, self.spi0.source, self.spi0_phy.source)
        m.d.comb += self.spi0_phy.sink.ready.eq(1)
        m.d.comb += self.spi0_phy.cs.eq(self.spi0.cs)

        # I2S TX/RX
        m.submodules.i2s_rx = self.i2s_rx
        m.submodules.i2s_tx = self.i2s_tx

        if not self.sim:
            mic = platform.request("mic", 0)

            m.d.comb += [
                mic.lrclk.o.eq(self.i2s_rx.lrclk),
                mic.clk.o.eq(self.i2s_rx.sclk),
                self.i2s_rx.sdin.eq(mic.data.i)
            ]

            amp = platform.request("amp", 0)
            m.d.comb += amp.en.o.eq(1)
            m.d.comb += amp.lrclk.o.eq(~self.i2s_tx.lrclk)
            m.d.comb += amp.clk.o.eq(self.i2s_tx.sclk)
            m.d.comb += amp.data.o.eq(self.i2s_tx.sdout)

        m.submodules.vocoder = self.vocoder
        wiring.connect(m, self.vocoder.sink, self.i2s_rx.source)
        wiring.connect(m, self.vocoder.source, self.i2s_tx.sink)

        # wishbone csr bridge
        if not self.sim:
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

    def build(self, name, build_dir):
        firmware_root = os.path.join( os.getcwd(),"../software/girlvoice")
        firmware_bin_path = os.path.join(firmware_root, "girlvoice.bin")
        GirlvoiceSoc.compile_firmware(firmware_root, firmware_bin_path)
        self.firmware_path = firmware_bin_path

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
            f.write(f"pub const HW_REV_MAJOR: u32        = {self.platform_class.version_major};\n")
            f.write(f"pub const CLOCK_SYNC_HZ: u32       = {self.clock_settings.frequencies.sync};\n")
            f.write(f"pub const CLOCK_FAST_HZ: u32       = {self.clock_settings.frequencies.fast};\n")
            f.write(f"pub const CLOCK_AUDIO_HZ: u32      = {self.clock_settings.frequencies.audio};\n")
            f.write(f"pub const SPIFLASH_BASE: usize     = 0x{self.spiflash_base:x};\n")
            f.write(f"pub const SPIFLASH_SZ_BYTES: usize = 0x{self.spiflash_size:x};\n")
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

    @staticmethod
    def compile_firmware(rust_fw_root, rust_fw_bin):
        print("Building SoC firmware...")
        subprocess.check_call([
            "cargo", "build", "--release"
            ], env=os.environ, cwd=rust_fw_root)
        subprocess.check_call([
            "cargo", "objcopy", "--release", "--", "-Obinary", rust_fw_bin
            ], env=os.environ, cwd=rust_fw_root)

class VerilatorPlatform():
    def __init__(self):
        self.files = {}

    def add_file(self, file_name, contents):
        self.files[file_name] = contents


if __name__ == "__main__":
    import amaranth.back.verilog as verilog
    soc = GirlvoiceSoc(sim=True)
    soc.build(name="", build_dir="")

    plat = VerilatorPlatform()
    print(list(soc.signature.flatten(soc)))
    with open(f"girlvoice_soc.v", "w") as f:
        f.write(
            verilog.convert(
                soc,
                name="girlvoice_soc",
                ports=[
                    # soc.clk
                ],
                emit_src=False,
                strip_internal_attrs=True,
                platform=plat
            )
        )