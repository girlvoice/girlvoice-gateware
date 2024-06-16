# girlvoice

The gateware repo for girlvoice, the real-time FPGA vocoder.

# Setup
After creating and entering a new python 3.11 venv do `pdm install` to install all required dependencies.

# Build

Run the following command to build the Litex softcore target for the Rev A board:
```
pdm run girlvoice/targets/girlvoice_litex.py --cpu-variant imac --toolchain=radiant --synth-mode=lse --csr-svd girlsoc.svd --build
```

This will generate a `.svd` file that must then be processed into a Peripheral Access Crate (PAC) for the rust-based firmware.


`pdm run girlvoice/lifcl_evn_top.py` to build for the CrossLinkNX evaluation board.

`pdm run girlvoice/girlvoice_rev_a.py` to build for the girlvoice rev A PCB.

