import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

@cocotb.test
async def soc_test(dut):
    sys_clk_freq = 60e6
    c = Clock(dut.clk, period=16.67, unit="ns")

    c.start()

    await Timer(5, unit="ms")



