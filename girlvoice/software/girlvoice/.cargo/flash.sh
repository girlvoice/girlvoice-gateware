#!/usr/bin/env bash

set -e
echo $1
# Create bin file
riscv64-linux-gnu-objcopy $1 -O binary girlvoice.bin

# Program iCEBreaker
python -m litex.tools.litex_term --kernel girlvoice.bin /dev/ttyUSB1