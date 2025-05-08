# girlvoice

The gateware repo for girlvoice, the real-time FPGA vocoder.

# Overview

Girlvoice is a hardware module intended to amplify and modulate a voice in real-time. While I hope to extend this project to a variety of voice synthesis and modulation techniques, I am currently focused on implementing a [channel vocoder](https://en.wikipedia.org/wiki/Vocoder).

This repo contains the [amaranth](https://github.com/amaranth-lang/amaranth) gateware cores responsible for implementing the digital signal processing algorithms for the vocoder. It also contains the rust firmware that runs on a RISC-V softcore (currently [VexRiscv](https://github.com/SpinalHDL/VexRiscv)). The firmware is responsible for initialization and control of on-board hardware peripherals like the smart amplifier (which drives the speaker) and audio codec (for external audio IO). The firmware also manages configuration of the DSP cores through memory-mapped gateware registers.

# Setup
After creating and entering a new python 3.11 venv do `pdm install` to install all required dependencies.

# Build

Run the following command to build the Litex softcore target for the Rev A board:
```
pdm run girlvoice/targets/girlvoice_litex.py --cpu-variant imac --toolchain=radiant --synth-mode=lse --csr-svd girlsoc.svd --build
```

This will generate a `.svd` file that must then be processed into a Peripheral Access Crate (PAC) for the rust-based firmware.
run: `svd2rust -i girlsoc.svd --target riscv` to create the PAC `lib.rs` file.


`pdm run girlvoice/girlvoice_rev_a.py` to build for the girlvoice rev A PCB.

