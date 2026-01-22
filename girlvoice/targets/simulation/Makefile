# Makefile

# defaults
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../girlvoice_soc.v
# /home/sage/programming_stuff/sage/girlvoice/girlvoice/soc/vendor/luna_soc/gateware/cpu/verilog/vexriscv/vexriscv_imac+dcache.v
VERILOG_SOURCES += $(PWD)/../../soc/vendor/vexiiriscv/verilog/VexiiRiscv_e4d384a1cc53d1eaee7cc009d8a25ddb.v
# use VHDL_SOURCES for VHDL files
EXTRA_ARGS += -Wno-CASEINCOMPLETE
EXTRA_ARGS += -Wno-WIDTHTRUNC -Wno-PINMISSING -Wno-WIDTHEXPAND -Wno-ASCRANGE -Wno-CMPCONST
EXTRA_ARGS += --trace --trace-fst --trace-structs

# COCOTB_TOPLEVEL is the name of the toplevel module in your Verilog or VHDL file
COCOTB_TOPLEVEL = girlvoice_soc

# COCOTB_TEST_MODULES is the basename of the Python test file(s)
COCOTB_TEST_MODULES = sim_soc

# include cocotb's make rules to take care of the simulator setup
include $(shell cocotb-config --makefiles)/Makefile.sim
