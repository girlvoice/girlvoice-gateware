#
# This file is part of LUNA.
#
# Copyright (c) 2020-2025 Great Scott Gadgets <info@greatscottgadgets.com>
# SPDX-License-Identifier: BSD-3-Clause

import os
import sys
import shutil
import logging
import tempfile
import argparse

from amaranth                import Elaboratable
from amaranth._unused        import MustUse

from luna                    import configure_default_logging
from luna.gateware.platform  import get_appropriate_platform, configure_toolchain


def top_level_cli(fragment, *pos_args, **kwargs):

    """ Runs a default CLI that assists in building and running SoC gateware.

        If the user's options resulted in the board being programmed, this returns the fragment
        that was programmed onto the board. Otherwise, it returns None.

        Parameters:
            fragment  -- The design to be built; or a callable that returns a fragment,
                         such as a Elaborable type. If the latter is provided, any keyword or positional
                         arguments not specified here will be passed to this callable.
    """

    # Disable UnusedElaboarable warnings until we decide to build things.
    # This is sort of cursed, but it keeps us categorically from getting UnusedElaborable warnings
    # if we're not actually buliding.
    MustUse._MustUse__silence = True

    # Configure logging.
    configure_default_logging()
    logging.getLogger().setLevel(logging.DEBUG)

    # If this isn't a fragment directly, interpret it as an object that will build one.
    name = fragment.__name__ if callable(fragment) else fragment.__class__.__name__
    if callable(fragment):
        fragment = fragment(*pos_args, **kwargs)

    # Make sure this fragment represents a SoC design.
    if not hasattr(fragment, "soc"):
        logging.error(f"Provided fragment '{name}' is not a SoC design")
        sys.exit(0)

    # Configure command arguments.
    parser = argparse.ArgumentParser(description=f"Gateware generation/upload script for '{name}' gateware.")
    parser.add_argument('--output', '-o', metavar='filename', help="Build and output a bitstream to the given file.")
    parser.add_argument('--erase', '-E', action='store_true',
         help="Clears the relevant FPGA's flash before performing other options.")
    parser.add_argument('--upload', '-U', action='store_true',
         help="Uploads the relevant design to the target hardware. Default if no options are provided.")
    parser.add_argument('--flash', '-F', action='store_true',
         help="Flashes the relevant design to the target hardware's configuration flash.")
    parser.add_argument('--dry-run', '-D', action='store_true',
         help="When provided as the only option; builds the relevant bitstream without uploading or flashing it.")
    parser.add_argument('--keep-files', action='store_true',
         help="Keeps the local files in the default `build` folder.")
    parser.add_argument('--fpga', metavar='part_number',
         help="Overrides build configuration to build for a given FPGA. Useful if no FPGA is connected during build.")
    parser.add_argument('--console', metavar="port",
         help="Attempts to open a convenience 115200 8N1 UART console on the specified port immediately after uploading.")

    # Configure SoC command arguments.
    parser.add_argument('--generate-c-header', action='store_true',
        help="If provided, a C header file for this design's SoC will be printed to the stdout. Other options ignored.")
    parser.add_argument('--generate-ld-script', action='store_true',
        help="If provided, a C linker script for design's SoC memory regions will be printed to the stdout. Other options ignored.")
    parser.add_argument('--generate-memory-x', action='store_true',
        help="If provided, a Rust linker script for design's SoC memory regions will be printed to the stdout. Other options ignored.")
    parser.add_argument('--generate-svd', action='store_true',
        help="If provided, a SVD description of this design's SoC will be printed to the stdout. Other options ignored.")
    parser.add_argument('--get-reset-address', action='store_true',
        help="If provided, the utility will print the cpu's reset address to stdout. Other options ignored.")

    # Parse command arguments.
    args = parser.parse_args()

    # If we have no other options set, build and upload the relevant file.
    if (args.output is None and not args.flash and not args.erase and not args.dry_run):
        args.upload = True

    # Once the device is flashed, it will self-reconfigure, so we
    # don't need an explicitly upload step; and it implicitly erases
    # the flash, so we don't need an erase step.
    if args.flash:
        args.erase = False
        args.upload = False

    # Select platform.
    platform = get_appropriate_platform()
    if platform is None:
        logging.error("Failed to identify a supported platform")
        sys.exit(1)

    # If we have a toolchain override, apply it to our platform.
    toolchain = os.getenv("LUNA_TOOLCHAIN")
    if toolchain:
        platform.toolchain = toolchain

    if args.fpga:
        platform.device = args.fpga

    # If we've been asked to generate a C header, generate -only- that.
    if args.generate_c_header:
        logging.info("Generating C header for SoC")
        from luna_soc.generate import c, introspect
        soc        = introspect.soc(fragment)
        memory_map = introspect.memory_map(soc)
        interrupts = introspect.interrupts(soc)
        c.Header(memory_map, interrupts).generate(file=None)
        sys.exit(0)

    # If we've been asked to generate C linker region info, generate -only- that.
    if args.generate_ld_script:
        logging.info("Generating C linker region info script for SoC")
        from luna_soc.generate import c, introspect
        soc        = introspect.soc(fragment)
        memory_map = introspect.memory_map(soc)
        reset_addr = introspect.reset_addr(soc)
        c.LinkerScript(memory_map, reset_addr).generate(file=None)
        sys.exit(0)

    # If we've been asked to generate Rust linker region info, generate -only- that.
    if args.generate_memory_x:
        logging.info("Generating Rust linker region info script for SoC")
        from luna_soc.generate import rust, introspect
        soc        = introspect.soc(fragment)
        memory_map = introspect.memory_map(soc)
        reset_addr = introspect.reset_addr(soc)
        rust.LinkerScript(memory_map, reset_addr).generate(file=None)
        sys.exit(0)

    # If we've been asked to generate a SVD description of the design, generate -only- that.
    if args.generate_svd:
        logging.info("Generating SVD description for SoC")
        from luna_soc.generate import introspect, svd
        soc        = introspect.soc(fragment)
        memory_map = introspect.memory_map(soc)
        interrupts = introspect.interrupts(soc)
        svd.SVD(memory_map, interrupts).generate(file=None)
        sys.exit(0)

    # If we've been asked for the cpu reset address, generate _only_ that.
    if args.get_reset_address:
        from luna_soc.generate import introspect
        soc        = introspect.soc(fragment)
        reset_addr = introspect.reset_addr(soc)
        print(f"0x{reset_addr:08x}")
        sys.exit(0)

    # If we'be been asked to erase the FPGA's flash before performing other options, do that.
    if args.erase:
        logging.info("Erasing flash...")
        platform.toolchain_erase()
        logging.info("Erase complete.")

    # Build the relevant files.
    build_dir = "build" if args.keep_files else tempfile.mkdtemp()
    try:
        build(args, fragment, platform, build_dir)

        # Return the fragment we're working with, for convenience.
        if args.upload or args.flash:
            return fragment

    # Clean up any directories created during the build process.
    finally:
        if not args.keep_files:
            shutil.rmtree(build_dir)

    return None


# - build commands ------------------------------------------------------------

def build(args, fragment, platform, build_dir):
    """ Top-level build command. Invokes the build steps for each artifact
        to be generated."""

    join_text = "and uploading gateware to attached" if args.upload else "for"
    logging.info(f"Building {join_text} {platform.name}...")
    logging.info(f"Build directory: {build_dir}")

    # Allow SoC to perform any pre-elaboration steps it wants.
    # This allows it to e.g. build a BIOS or equivalent firmware.
    _build_pre(args, fragment, platform, build_dir)

    # Generate the design bitstream.
    products = _build_gateware(args, fragment, platform, build_dir)

    # Perform post-build steps
    _build_post(args, fragment, platform, build_dir, products)


def _build_pre(args, fragment, platform, build_dir):
    """ Perform any pre-elaboration steps for the design. e.g. build a
        BIOS or equivalent firmware."""

    # Call SoC build function if it has one
    soc_build = getattr(fragment.soc, "build", None)
    if callable(soc_build):
        logging.info("Performing SoC build steps")
        soc_build(name="soc", build_dir=build_dir)


def _build_gateware(args, fragment, platform, build_dir):
    """ Build gateware for the design."""

    # Configure toolchain.
    if not configure_toolchain(platform):
        logging.info(f"Failed to configure the toolchain for: {platform.toolchain}")
        logging.info(f"Continuing anyway.")

    # Now that we're actually building, re-enable Unused warnings.
    MustUse._MustUse__silence = False

    # Perform the build.
    products = platform.build(
        fragment,
        do_program=args.upload,
        build_dir=build_dir
    )

    # Disable UnusedElaboarable warnings again.
    MustUse._MustUse__silence = True

    logging.info(f"{'Upload' if args.upload else 'Build'} complete.")

    return products


def _build_post(args, fragment, platform, build_dir, products):
    """ Perform post-build steps."""

    # If we're flashing the FPGA's flash, do so.
    if args.flash:
        logging.info("Programming flash...")
        platform.toolchain_flash(products)
        logging.info("Programming complete.")

    # If we're outputting a file, write it.
    if args.output:
        bitstream = products.get("top.bit")
        with open(args.output, "wb") as f:
            f.write(bitstream)

    # If we're expecting a console, open one.
    if args.console:
        import serial.tools.miniterm

        # Clear our arguments, so they're not parsed by miniterm.
        del sys.argv[1:]

        # Run miniterm with our default port and baudrate.
        serial.tools.miniterm.main(default_port=args.console, default_baudrate=115200)
