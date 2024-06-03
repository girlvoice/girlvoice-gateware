from migen import *

from litex.gen import *
# from litex.soc.interconnect.csr import *
from litex.soc.interconnect import wishbone
from girlvoice.platform.nexus_utils import lmmi


class LMMItoWishbone(Module):

    def __init__(self):
        self.bus = bus = wishbone.Interface(data_width=8, adr_width=8, addressing="word")

        self.lmmi = lmmi.Interface(data_width=8, adr_width=8)



class NexusI2CMaster(LiteXModule):

    def __init__(self, use_hard_io=True):

        NBASE_DELAY = "0b1010"

        alt_io_en = "IO" if use_hard_io else "FABRIC"

        self.scl_o = Signal()
        self.sda_o = Signal()

        self.scl_oe = Signal()
        self.sda_oe = Signal()

        self.scl_i = Signal()
        self.sda_i = Signal()

        if use_hard_io:
            self.alt_scl_o = Signal()
            self.alt_sda_o = Signal()

            self.alt_scl_oen = Signal()
            self.alt_sda_oen = Signal()

            self.alt_scl_i = Signal()
            self.alt_sda_i = Signal()

        self.i2c_bus_busy = Signal()

        self.bus = bus = wishbone.Interface(data_width=32, adr_width=32, addressing="word")
        self.interrupt = Signal()

        self.request_i = bus.stb
        self.wr_rdn_i = bus.we
        self.wdata_i = bus.dat_w[0:8]
        self.offset_i = bus.adr[0:8]

        self.rdata_o = bus.dat_r[0:8]
        self.rdata_valid_o = bus.ack
        self.ready_o = Signal()

        self.i2c_rstn = Signal()
        self.fifo_rst = Signal()
        self.cont_rd_complete = Signal()

        self.rx_fifo_full = Signal()
        self.rx_fifo_almost_full = Signal()
        self.rx_fifo_empty = Signal()

        self.tx_fifo_full = Signal()
        self.tx_fifo_almost_empty = Signal()
        self.tx_fifo_empty = Signal()
        self.params = {}
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

            p_GSR = "ENABLED",
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
            p_REGI2CBR = "0b0000101110",                     # I2C Clock Pre-Scale Register value
            p_TSPTIMERVALUE = "0b10010010111"           # Value that will be loaded into a down counter. This value will ensure I2C timing specification for Start/Repeated Start signal is met.
        )

        self.specials += Instance(
            "I2CFIFO",
            **self.params,
            i_LMMICLK = ClockSignal("sys"),
            i_LMMIRESET_N = ResetSignal("sys"),
            i_LMMIREQUEST = self.request_i,
            i_LMMIWRRD_N = self.wr_rdn_i,
            i_LMMIOFFSET = self.offset_i,
            i_LMMIWDATA = self.wdata_i,
            o_LMMIRDATA = self.rdata_o,
            o_LMMIRDATAVALID = self.rdata_valid_o,
            o_LMMIREADY = self.ready_o,
            i_ALTSCLIN = self.alt_scl_i,
            o_ALTSCLOUT = self.alt_scl_o,
            o_ALTSCLOEN = self.alt_scl_oen,
            i_ALTSDAIN = self.alt_sda_i,
            o_ALTSDAOUT = self.alt_sda_o,
            o_ALTSDAOEN = self.alt_sda_oen,
            o_BUSBUSY = self.i2c_bus_busy,
            i_FIFORESET = self.fifo_rst,
            i_I2CLSRRSTN = self.i2c_rstn,
            # .INSLEEP(insleep_o),
            o_IRQ = self.interrupt,
            o_MRDCMPL = self.cont_rd_complete,
            o_RXFIFOAF = self.rx_fifo_almost_full,
            o_RXFIFOE = self.rx_fifo_empty,
            o_RXFIFOF = self.rx_fifo_full,
            i_SCLIN = self.scl_i,
            o_SCLOE = self.scl_oe,
            # o_SCLOEN = self.scl_oe_n_o,
            o_SCLOUT = self.scl_o,
            i_SDAIN = self.sda_i,
            o_SDAOE = self.sda_oe,
            # .SDAOEN(sdaoe_n_o),
            o_SDAOUT = self.sda_o,
            # .SLVADDRMATCH(slvaddrmatch_o),
            # .SLVADDRMATCHSCL(slvaddrmatchscl_o),
            # .SRDWR(srdwr_o),
            o_TXFIFOAE = self.tx_fifo_almost_empty,
            o_TXFIFOE = self.tx_fifo_empty,
            o_TXFIFOF = self.tx_fifo_full
        )