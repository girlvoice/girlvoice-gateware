from amaranth import *
from amaranth.lib import wiring
from amaranth.lib.wiring import In

from amaranth_soc.memory import MemoryMap
from girlvoice.platform.nexus_utils import lmmi_am as lmmi

'''
Wrapper for the Lattice I2CFIFO hard IP on Nexus devices
'''
class I2CFIFO(wiring.Component):

    lmmi: In(lmmi.Signature(addr_width=8, data_width=8))
    def __init__(self, scl_freq: int, use_hard_io: bool):

        alt_io_en = "IO" if use_hard_io else "FABRIC"
        self.params = {}
        assert scl_freq in [100e3, 400e3], "Invalid I2C frequency"

        NBASE_DELAY = "0b1010"
        self.params.update(
            p_BRNBASEDELAY = NBASE_DELAY,       # The I2CBRMSB [7:4] is utilized for trimming the Base Delay which is combined with I2CC1 [3:2] to achieve the SDA output delay to meet the I2C Specification requirement (300ns).
            # General config registers
            p_CR1CKDIS = "DIS",     # Enable/disable clock streching in FIFO mode
            p_CR1FIFOMODE = "FIFO",          # Enable FIFO mode. 0 for register mode, 1 for FIFO mode
            p_CR1GCEN = "DIS",       # Enable general call response in slave mode
            p_CR1I2CEN = "EN",                  # Enable I2C core
            p_CR1SDADELSEL = "NDLY2",       # SDA output delay select - These two bits select the output delay (in Number of clk cycles. The Base Delay is set by MSB of the I2CBRMSB)
            p_CR1SLPCLKEN = "DIS",   # Sleep Clock Enable - Enables sleep clock to control fabric interface to continue I2C master FIFO operations during sleep.
            p_CR2CORERSTN = "DIS",              # Core Reset - Resets the I2C core
            p_CR2HARDTIE = "NOTIE",            # Peripherial address hard tie disable. Allows for setting the 2 LSB of the slave address, otherwise they are just 00.
            p_CR2INTCLREN = "DIS",              # Auto interrupt clear enable. If set, the interrupt flag is automatically cleared after the interrupt status registers are read.
            p_CR2MRDCMPLWKUP = "DIS",  # Documentation unclear. All set as disabled in Radiant.
            p_CR2RXFIFOAFWKUP = "DIS",
            p_CR2SLVADDRWKUP = "DIS",

            # p_GSR = "ENABLED",
            p_I2CRXFIFOAFVAL = "0b11110",
            p_I2CSLVADDRA = "0b0000000011",
            p_I2CTXFIFOAEVAL = "0b0011",
            p_INTARBLIE = "DIS",
            p_INTBUSFREEIE = "DIS",
            p_INTHGCIE = "DIS",
            p_INTMRDCMPLIE = "DIS",
            p_INTRNACKIEORRSVD = "DIS",
            p_INTRSVDORTROEIE = "DIS",
            p_INTRSVDORTRRDYIE = "DIS",
            p_INTRXOVERFIEORRSVD = "DIS",
            p_INTRXUNDERFIE = "DIS",
            p_INTTXOVERFIE = "DIS",
            p_INTTXSERRIEORRSVD = "DIS",
            p_LMMI_EXTRA_ONE = "DIS",                   # The comment in Radiant is literally "???"
            p_LMMI_EXTRA_TWO = "DIS",                   # The comment in Radiant is literally "???"
            p_NCRALTIOEN = alt_io_en,                   # Enables Alternate SCL & SDA Path to Hard IO
            p_NCRFILTERDIS = "DIS",                     # Soft Trim Enable - Enables soft trimming of the capacitance of the 50ns Filter and 50ns Delay.
            p_NCRSDAINDLYEN = "DIS",               # Enables 50ns Analog SDA Input Delay
            p_NCRSDAOUTDLYEN = "DIS",                   # Enables 50ns Analog SDA Output Delay
            p_NONUSRTESTSOFTTRIMEN = "DIS",             # Enables soft trimming of the capacitance of the 50ns Filter and 50ns Delay.
            p_NONUSRTSTSOFTTRIMVALUE = "0b000",         # Capacitance trim value for 50ns Filter and 50ns Delay.  Default on power up is 3'b000, after a clock cycle this value with take current hard trim value.
            p_REGI2CBR = "0b0010010110",                     # I2C Clock Pre-Scale Register value FSCL = FSOURCE / (4 * (I2CBR[9:0] + 1))
            p_TSPTIMERVALUE = "0b10010010111"           # Value that will be loaded into a down counter. This value will ensure I2C timing specification for Start/Repeated Start signal is met. Counted down against the system clock.
        )

        if use_hard_io:
            self.alt_scl_o = Signal()
            self.alt_sda_o = Signal()

            self.alt_scl_oen = Signal()
            self.alt_sda_oen = Signal()

            self.alt_scl_i = Signal()
            self.alt_sda_i = Signal()

            self.params.update(
                i_ALTSCLIN = self.alt_scl_i,
                o_ALTSCLOUT = self.alt_scl_o,
                o_ALTSCLOEN = self.alt_scl_oen, # For some reason the only output signals for the hard-IO is the inverted output-enable
                i_ALTSDAIN = self.alt_sda_i,
                o_ALTSDAOUT = self.alt_sda_o,
                o_ALTSDAOEN = self.alt_sda_oen,
            )
        else:
            self.scl_o = Signal()
            self.sda_o = Signal()

            self.scl_oe = Signal()
            self.sda_oe = Signal()

            self.scl_i = Signal()
            self.sda_i = Signal()

            self.params.update(
                i_SCLIN = self.scl_i,
                o_SCLOUT = self.scl_o,
                o_SCLOE = self.scl_oe, # For some reason the only output signals for the hard-IO is the inverted output-enable
                i_SDAIN = self.sda_i,
                o_SDAOUT = self.sda_o,
                o_SDAOE = self.sda_oe,
            )

        super().__init__()

        self.lmmi.memory_map = MemoryMap(addr_width=self.lmmi.addr_width, data_width=self.lmmi.data_width)

    def elaborate(self, platform):
        m = Module()

        self.i2c_rstn = Signal()
        self.fifo_rst = Signal()
        self.cont_rd_complete = Signal()

        self.rx_fifo_full = Signal()
        self.rx_fifo_almost_full = Signal()
        self.rx_fifo_empty = Signal()

        self.tx_fifo_full = Signal()
        self.tx_fifo_almost_empty = Signal()
        self.tx_fifo_empty = Signal()

        self.i2c_bus_busy = Signal()
        self.params.update(

            i_LMMICLK = ClockSignal(),
            i_LMMIRESET_N = ~ResetSignal(),
            i_LMMIREQUEST = self.lmmi.request,
            i_LMMIWRRD_N = self.lmmi.wr_rdn,
            i_LMMIOFFSET = self.lmmi.offset,
            i_LMMIWDATA = self.lmmi.wdata,
            o_LMMIRDATA = self.lmmi.rdata,
            o_LMMIRDATAVALID = self.lmmi.rdata_valid,
            o_LMMIREADY = self.lmmi.ready,
            o_BUSBUSY = self.i2c_bus_busy,
            i_FIFORESET = self.fifo_rst,
            i_I2CLSRRSTN = True,
        )
        m.submodules.i2c_fifo = Instance("I2CFIFO", **self.params)

        return m