# girlvoice

The gateware repo for girlvoice, the real-time FPGA vocoder.

# Setup
After creating and entering a new python venv do `pdm install` to install all required dependencies.

# Build
`pdm run girlvoice/lifcl_evn_top.py` to build for the CrossLinkNX evaluation board.

`pdm run girlvoice/girlvoice_rev_a.py` to build for the girlvoice rev A PCB.

