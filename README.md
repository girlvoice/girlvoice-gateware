# girlvoice

The gateware and firmware repo for girlvoice, the real-time FPGA vocoder.

# Overview

Girlvoice is a hardware module intended to amplify and modulate a voice in real-time. While I hope to extend this project to a variety of voice synthesis and modulation techniques, I am currently focused on implementing a [channel vocoder](https://en.wikipedia.org/wiki/Vocoder).

This repo contains the [amaranth](https://github.com/amaranth-lang/amaranth) gateware cores responsible for implementing the digital signal processing algorithms for the vocoder. It also contains the rust firmware that runs on a RISC-V softcore (currently [VexRiscv](https://github.com/SpinalHDL/VexRiscv)). The firmware is responsible for initialization and control of on-board hardware peripherals like the smart amplifier (which drives the speaker) and audio codec (for external audio IO). The firmware also manages configuration of the DSP cores through memory-mapped gateware registers.

The top-level gateware modules can be found in `girlvoice/targets`. This currently includes a target for the design including a LiteX SoC, and a pure Amaranth target with just the Vocoder.
The pure Amaranth target requires custom hardware to work properly.

The DSP gateware cores are contained in `girlvoice/dsp`.

The IO peripheral gateware cores are in `girlvoice/io`.

The platform-specific configuration and gateware is in `girlvoice/platform`. This includes utility modules for working with the Lattice Nexus FPGA, as well as platform pin configuration files.

The rust firmware for the SoC is in `girlvoice/software`.

# Prerequisites

## Radiant Docker Setup

The build uses Lattice Radiant running in Docker. Set up the radiant-docker container first:

1. Clone the `radiant-docker` repo alongside this repo:
   ```
   girlvoice/
   ├── girlvoice-gateware/
   └── radiant-docker/
   ```

2. Obtain `2025.1.0.39.0_Radiant_lin.run` and place it in `radiant-docker/`.

3. Build the Docker container:
   ```bash
   cd radiant-docker
   docker build --tag radiant-container -f Dockerfile.base .
   # On Apple Silicon, add: --platform linux/amd64
   ```

# Setup

```bash
python -m venv .
pdm install
```

# Build (for target LUNA-SOC)

Make sure Docker is running, then:
```bash
pdm run build
```

Note: The build process can take several minutes.

# Flash

```bash
pdm run flash
```

# Alternative Targets

## LiteX Target

```bash
pdm run python girlvoice/targets/girlvoice_litex.py --cpu-variant imac --toolchain=radiant --synth-mode=lse --csr-svd girlsoc.svd --build
```

This generates a `.svd` file for the Peripheral Access Crate (PAC):
```bash
svd2rust -i girlsoc.svd --target riscv
```
