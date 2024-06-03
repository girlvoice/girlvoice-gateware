#!/usr/bin/env python3

from amaranth import *
from amaranth.sim import Simulator
from math import log2


CMD_READ = 0x01
CMD_WRITE = 0x00

REG_SIZE = 8
WORD_SIZE = 16
class I2CInitiator(Elaboratable):
    def __init__(self, clk_freq, i2c_clk_freq) -> None:
        if (int(clk_freq) % int(i2c_clk_freq)) != 0:
            raise ValueError(f"i2c_clk_freq ({i2c_clk_freq}) must be a divisor of clk_freq ({clk_freq})")

        def is_power_of_two(n):
            return n != 0 and (n & (n - 1)) == 0

        self.CLKS_PER_SCLK = round(clk_freq / i2c_clk_freq)
        if (not is_power_of_two(round(self.CLKS_PER_SCLK))):
            raise ValueError(f"i2c_clk_freq ({i2c_clk_freq}) must be a power of two divisor of clk_freq ({clk_freq})")

        if (int(clk_freq) / int(i2c_clk_freq)) < 2:
            raise ValueError(f"i2c_clk_freq ({i2c_clk_freq/1000000} MHz) must be less than half of clk_freq ({clk_freq/1000000} MHz)")

        if (int(i2c_clk_freq) > 400_000):
            raise ValueError(f"i2c_clk_freq ({i2c_clk_freq/1000000} MHz) cannot be more than 400 kHz")

        self.data_i = Signal(8)
        self.write_strb_i = Signal()
        self.read_strb_i = Signal()

        self.sda_o = Signal(reset=1)
        self.sclk_o = Signal(reset=1)

        self.sda_i = Signal()
        self.sclk_i = Signal()

        self.sda_oe = Signal()
        self.sclk_oe = Signal()

        self.subnode_address_i = Signal(8)
        self.reg_address_i = Signal(8)

        self.dev_reg_address_i = Signal(MAX9611_I2C_Addr)

        self.data_o = Signal(16)
        self.busy_o = Signal()
        self.data_ready_o = Signal()


    def elaborate(self, platform):
        m = Module()

        sub_addr_shreg = Signal(REG_SIZE)
        reg_addr_shreg = Signal(REG_SIZE)
        data_shreg = Signal(REG_SIZE)

        shift_out = Signal(REG_SIZE)
        shift_in = Signal(WORD_SIZE)

        do_read = Signal()
        do_write = Signal()
        do_shift_out = Signal() # Shift out on SCLK falling edge
        do_shift_in = Signal() # Shift in on SCLK rising edge
        clk_last = Signal()

        ack_reg = Signal()

        clk_cnt = Signal(range(self.CLKS_PER_SCLK))
        SCLK_BIT = round(log2(self.CLKS_PER_SCLK) - 1)

        release_sclk = Signal()

        bit_cnt = Signal(range(16 + 1))
        m.d.comb += [
            self.sclk_o.eq((~clk_cnt[SCLK_BIT]) | ~self.busy_o | release_sclk),
            self.sclk_oe.eq(~self.sclk_o), # Output allowed to float high when transmitting a 1
            self.sda_oe.eq(~self.sda_o),   # Output allowed to float high when transmitting a 1
            do_shift_out.eq(~self.sclk_o & clk_last),
            do_shift_in.eq(self.sclk_o & ~clk_last),

            self.subnode_address_i.eq(self.dev_reg_address_i.dev_addr_u8),
            self.reg_address_i.eq(self.dev_reg_address_i.reg_addr_u8),
            ]

        setup = Signal()

        with m.If(clk_last != self.sclk_o):
            m.d.sync += clk_last.eq(self.sclk_o)

        with m.FSM() as fsm:
            with m.State("IDLE"):
                m.d.sync += [
                    self.busy_o.eq(0),
                    clk_cnt.eq(0),
                    self.sda_o.eq(1),
                    release_sclk.eq(0),
                    ]

                with m.If(self.write_strb_i | self.read_strb_i):
                    m.d.sync += [
                        do_read.eq(self.read_strb_i),
                        do_write.eq(self.write_strb_i),
                        sub_addr_shreg.eq(self.subnode_address_i),
                        reg_addr_shreg.eq(self.reg_address_i),
                        data_shreg.eq(self.data_i),
                        self.busy_o.eq(1),
                        self.data_ready_o.eq(0),
                        setup.eq(1),
                        ]
                    m.next = "START"

            with m.State("START"):
                m.d.sync += [
                    self.busy_o.eq(1),
                    self.sda_o.eq(0),
                    clk_cnt.eq(clk_cnt + 1),
                    bit_cnt.eq(0),
                    ]
                with m.If(~self.sclk_o):
                    m.d.sync += shift_out.eq(sub_addr_shreg),
                    m.next = "WRITE"

            with m.State("START_REPEAT"):
                m.d.sync += clk_cnt.eq(clk_cnt + 1)


                with m.If(do_shift_in):
                    m.d.sync += [
                        # self.sda_o.eq(0),
                        # release_sclk.eq(0),
                    ]
                    m.next = "START_REPEAT_SCLK_HI"

            with m.State("START_REPEAT_SCLK_HI"):
                m.d.sync += clk_cnt.eq(clk_cnt + 1)
                with m.If(clk_cnt[SCLK_BIT-1]):
                    m.d.sync += self.sda_o.eq(0)
                    # m.d.sync += clk_cnt.eq(0)
                    # m.next = "BUFFER"
                with m.If(do_shift_out):
                    m.next = "READ_SUB_ADDR"

            # Write the target subnode address to the bus then wait for ACK
            # with m.State("WRITE_SUB_ADDR"):
            #     m.d.sync += [
            #         clk_cnt.eq(clk_cnt + 1),
            #         self.sda_o.eq(shift_out[7])
            #         ]
            #     with m.If(do_shift_out):
            #         m.d.sync += [
            #             bit_cnt.eq(bit_cnt + 1),
            #             shift_out.eq(shift_out << 1),
            #         ]
            #         with m.If(bit_cnt == 7):
            #             m.d.sync += [
            #                 bit_cnt.eq(0),
            #                 shift_out.eq(reg_addr_shreg),
            #             ]
            #             m.next = "SUB_ADDR_ACK"

            with m.State("WRITE"):
                m.d.sync += [
                    clk_cnt.eq(clk_cnt + 1),
                    self.sda_o.eq(shift_out[7])
                    ]
                with m.If(do_shift_out):
                    m.d.sync += [
                        bit_cnt.eq(bit_cnt + 1),
                        shift_out.eq(shift_out << 1),
                    ]
                    with m.If(bit_cnt == 7):
                        m.d.sync += [
                            bit_cnt.eq(0),
                        ]
                        m.next = "SUB_ACK"

            # with m.State("DELAY_DEBUG"):
            #     m.d.sync += [
            #         clk_cnt.eq(clk_cnt + 1),
            #         self.sda_o.eq(1)        # Release SDA
            #         ]
            #     with m.If(do_shift_out):
            #         m.next = "SUB_ACK"
            with m.State("SUB_ACK"):
                m.d.sync += [
                    clk_cnt.eq(clk_cnt + 1),
                    self.sda_o.eq(1)        # Release SDA
                    ]
                with m.If(do_shift_in):
                    m.d.sync += ack_reg.eq(~self.sda_i) # Sample SDA on SCLK rising edge when listening for ACK

                with m.If(do_shift_out):
                    with m.If(ack_reg):
                        with m.If(setup):
                            m.d.sync += shift_out.eq(reg_addr_shreg),
                            m.d.sync += setup.eq(0)
                            m.next = "WRITE"
                        with m.Elif(do_read):
                            m.d.sync += [
                                # release_sclk.eq(1),
                                # clk_cnt.eq(0),
                                shift_out.eq(sub_addr_shreg | CMD_READ),
                                ]
                            m.next = "START_REPEAT"
                        with m.Elif(do_write):
                            m.d.sync += shift_out.eq(data_shreg)
                            m.d.sync += do_write.eq(0)
                            m.next = "WRITE"
                        with m.Else():
                            m.next = "STOP_SCLK_HI"
                    with m.Else():
                        m.next = "IDLE"
            # # Wait for ACK from subnode after sending subnode address. Then write the target register address to the bus
            # with m.State("SUB_ADDR_ACK"):
            #     m.d.sync += [
            #         clk_cnt.eq(clk_cnt + 1),
            #         self.sda_o.eq(1)        # Release SDA
            #         ]
            #     with m.If(do_shift_in):
            #         m.d.sync += ack_reg.eq(~self.sda_i) # Sample SDA on SCLK rising edge when listening for ACK

            #     with m.If(do_shift_out):
            #         with m.If(ack_reg):
            #             m.next = "WRITE_REG_ADDR"
            #         with m.Else():
            #             m.next = "IDLE"

            # with m.State("DATA_ACK"):
            #     m.d.sync += [
            #         clk_cnt.eq(clk_cnt + 1),
            #         self.sda_o.eq(1)        # Release SDA
            #         ]
            #     with m.If(do_shift_in):
            #         m.d.sync += ack_reg.eq(~self.sda_i) # Sample SDA on SCLK rising edge when listening for ACK

            #     with m.If(do_shift_out):
            #         with m.If(ack_reg):
            #             m.next = "STOP_SCLK_HI"
            #         with m.Else():
            #             m.next = "IDLE"

            # with m.State("REG_ADDR_ACK"):
            #     m.d.sync += [
            #         clk_cnt.eq(clk_cnt + 1),
            #         self.sda_o.eq(1)        # Release SDA
            #         ]
            #     with m.If(do_shift_in):
            #         m.d.sync += ack_reg.eq(~self.sda_i) # Sample SDA on SCLK rising edge when listening for ACK

            #     with m.If(do_shift_out):
            #         with m.If(ack_reg):
            #             with m.If(do_read):
            #                 m.d.sync += [
            #                     release_sclk.eq(1),
            #                     clk_cnt.eq(0),
            #                     shift_out.eq(sub_addr_shreg | CMD_READ),
            #                     ]
            #                 m.next = "START_REPEAT"
            #             with m.Elif(do_write):
            #                 m.d.sync += shift_out.eq(data_shreg),
            #                 m.next = "WRITE_DATA"
            #         with m.Else():
            #             m.next = "IDLE"

            # with m.State("WRITE_REG_ADDR"):
            #     m.d.sync += [
            #         clk_cnt.eq(clk_cnt + 1),
            #         self.sda_o.eq(shift_out[7])
            #         ]
            #     with m.If(do_shift_out):
            #         m.d.sync += [
            #             bit_cnt.eq(bit_cnt + 1),
            #             shift_out.eq(shift_out << 1),
            #         ]
            #         with m.If(bit_cnt == 7):
            #             m.d.sync += bit_cnt.eq(0)
            #             m.next = "REG_ADDR_ACK"

            # with m.State("WRITE_DATA"):
            #     m.d.sync += [
            #         clk_cnt.eq(clk_cnt + 1),
            #         self.sda_o.eq(shift_out[7])
            #         ]
            #     with m.If(do_shift_out):
            #         m.d.sync += [
            #             bit_cnt.eq(bit_cnt + 1),
            #             shift_out.eq(shift_out << 1),
            #         ]
            #         with m.If(bit_cnt == 7):
            #             m.d.sync += bit_cnt.eq(0)
            #             m.next = "DATA_ACK"

            with m.State("READ_SUB_ADDR"):
                m.d.sync += [
                    clk_cnt.eq(clk_cnt + 1),
                    self.sda_o.eq(shift_out[7])
                    ]
                with m.If(do_shift_out):
                    m.d.sync += [
                        bit_cnt.eq(bit_cnt + 1),
                        shift_out.eq(shift_out << 1),
                    ]
                    with m.If(bit_cnt == 7):
                        m.d.sync += [
                            bit_cnt.eq(0),   # Reset bit counter for next operation
                            shift_in.eq(0),  # Clear input shreg in anticipation of reciving data from subnode
                        ]
                        m.next = "READ_ACK"

            with m.State("READ_ACK"):
                m.d.sync += [
                    clk_cnt.eq(clk_cnt + 1),
                    self.sda_o.eq(1)        # Release SDA so subnode can ACK
                    ]
                with m.If(self.sclk_o):
                    with m.If(~self.sda_i):
                        m.next = "READ_SHIFT"
                    with m.Else():
                        m.next = "IDLE"

            with m.State("READ_SHIFT"):
                m.d.sync += [
                    clk_cnt.eq(clk_cnt + 1),
                    self.sda_o.eq(1)        # Release SDA so subnode can transmit
                    ]
                with m.If(do_shift_in):
                    m.d.sync += [
                        bit_cnt.eq(bit_cnt + 1),
                        shift_in.eq((shift_in << 1) | self.sda_i),
                    ]
                with m.If(do_shift_out):
                    with m.If(bit_cnt == 8):
                        m.next = "MAIN_ACK"
                    with m.Elif(bit_cnt == 16):
                        m.d.sync += [
                            self.data_o.eq(shift_in[4:]),
                            bit_cnt.eq(0),
                            self.data_ready_o.eq(1),
                        ]
                        m.next = "MAIN_NACK"

            with m.State("MAIN_ACK"):
                m.d.sync += clk_cnt.eq(clk_cnt + 1)
                m.d.sync += self.sda_o.eq(0)

                with m.If(do_shift_out):
                    m.next = "READ_SHIFT"

            with m.State("MAIN_NACK"):
                m.d.sync += clk_cnt.eq(clk_cnt + 1)
                m.d.sync += self.sda_o.eq(1)

                with m.If(do_shift_out):
                    m.next = "STOP_SCLK_HI"

            # First half of stop condition brings SCLK high
            with m.State("STOP_SCLK_HI"):
                m.d.sync += [
                    clk_cnt.eq(clk_cnt + 1),
                    self.sda_o.eq(0),
                    ]
                with m.If(do_shift_in):
                    m.next = "STOP_SDA_HI"

            # Second half of stop condition brings SDA high after 1/4 SCLK period
            with m.State("STOP_SDA_HI"):
                m.d.sync += [
                    clk_cnt.eq(clk_cnt + 1),
                    self.sda_o.eq(0),
                    release_sclk.eq(1),
                    ]
                with m.If(clk_cnt[SCLK_BIT-1]):
                    m.d.sync += self.sda_o.eq(1)
                    m.d.sync += clk_cnt.eq(0)
                    m.next = "BUFFER"

            # Data sheet requires 1.3us buffer time between transactions (1/2 of min SCLK period)
            with m.State("BUFFER"):
                m.d.sync += clk_cnt.eq(clk_cnt + 1)
                with m.If(clk_cnt[SCLK_BIT]):
                    m.next = "IDLE"


        return m

def main():
    m = Module()
    cd_sync = ClockDomain("sync")
    m.domains += cd_sync

    dut = MAX9611Main(clk_freq=48e6, i2c_clk_freq=375e3)
    m.submodules += dut

    test_addr = 0xE0
    test_reg = 0x05
    test_data = 0x69

    sclk_rising = Signal()
    sclk_falling = Signal()
    sclk_last = Signal()
    sub_sda_out = Signal()
    m.d.comb += [
        dut.data_i.eq(0),
        dut.dev_reg_address_i.dev_addr_u8.eq(test_addr),
        dut.dev_reg_address_i.reg_addr_u8.eq(test_reg),
        dut.data_i.eq(test_data),
        sclk_rising.eq(dut.sclk_o & ~sclk_last),
        sclk_falling.eq(~dut.sclk_o & sclk_last),

        # dut.sda_i.eq((sub_sda_out | dut.sda_o) & 1),
    ]
    with m.If(dut.sda_oe):
        m.d.comb += dut.sda_i.eq(dut.sda_o)
    with m.Else():
        m.d.comb += dut.sda_i.eq(sub_sda_out)

    with m.If(sclk_last != dut.sclk_o):
        m.d.sync += sclk_last.eq(dut.sclk_o)

    def read_bit():
        while (yield (~sclk_rising)):
            # print("Waiting for rising edge")
            yield
        bit = yield (dut.sda_o)

        while (yield (~sclk_falling)):
            # print("Waiting for falling edge")
            if (yield dut.sda_o) != bit:
                raise ValueError("SDA changed during bit read")
            yield
        return bit

    def read_byte():
        byte = 0
        for i in range(8):
            bit = yield from read_bit()
            # print(f"Read bit {bit}")
            byte = (byte << 1) | (bit)
            yield
        return byte


    def write_bit(bit):

        while (yield dut.sclk_o):  # Wait for SCLK to be low
            yield

        yield sub_sda_out.eq(bit)

        while (yield (~sclk_rising)): # Wait for SCLK to be high
            yield

        for _ in range(dut.CLKS_PER_SCLK//4):
            yield
        yield
        yield sub_sda_out.eq(0)

    def write_byte():
        byte = test_data
        for i in range(8):
            yield from write_bit((byte & 0x80) >> 7)
            byte = byte << 1
            yield

    def send_ack():
        yield sub_sda_out.eq(0)
        timeout = 0
        yield
        while (yield (~sclk_rising)):
            assert (yield dut.sda_oe) == 0, "Controller must release SDA during ACK"
            timeout += 1
            if timeout > 5000:
                assert False
            yield
        for _ in range(dut.CLKS_PER_SCLK//4):
            yield
        yield sub_sda_out.eq(1)

    def wait_for_stop():
        while (yield (~sclk_rising)):
            yield
        assert (yield dut.sda_o) == 0, "SDA must be low during stop condition"
        timer = 0
        while (yield (~dut.sda_o)):
            timer += 1
            yield
        stop_setup = timer * 1/48e6 * 1e6
        assert stop_setup >= 0.6, f"Stop setup time {stop_setup}us must be at least 0.6us"

    def setup():
        yield
        byte = yield from read_byte()
        assert byte == test_addr, f"Expected {test_addr:02X} got {byte:02X}"
        print(f"Read {byte:02X}")

        yield from send_ack()
        yield
        byte = yield from read_byte()
        assert byte == test_reg, f"Expected {test_reg:02X} got {byte:02X}"
        print(f"Read {byte:02X}")

        yield from send_ack()
        yield

    def write_test_bench():

        for i in range(100):
            yield
        # yield dut.read_strb_i.eq(1)
        # yield
        # yield dut.read_strb_i.eq(0)
        yield dut.write_strb_i.eq(1)
        yield
        yield dut.write_strb_i.eq(0)

        yield from setup()

        byte = yield from read_byte()
        assert byte == test_data, f"Expected {test_data:02X} got {byte:02X}"
        print(f"Read {byte:02X}")

        yield from send_ack()
        yield

        yield from wait_for_stop()

        while (yield dut.busy_o):
            yield

    def wait_for_rstart():
        while (yield (~sclk_rising)):
            yield
        assert (yield dut.sda_o) == 1, "SDA must be high during repeated start condition"
        timer = 0

        while (yield dut.sda_o):
            timer += 1
            yield
        stop_setup = timer * 1/48e6 * 1e6
        assert stop_setup >= 0.6, f"Repeated start setup time {stop_setup}us must be at least 0.6us"

    def wait_for_main_ack():

        while (yield (~sclk_rising)):  # Wait for SCLK rise
            yield

        for _ in range(dut.CLKS_PER_SCLK//4):
            yield
        assert (yield dut.sda_o) == 0, "SDA must be low during master ACK"

    def wait_for_main_nack():

        while (yield (~sclk_rising)):  # Wait for SCLK rise
            yield

        for _ in range(dut.CLKS_PER_SCLK//4):
            yield
        assert (yield dut.sda_o) == 1, "SDA must be high during master ACK"

    def read_test_bench():
        yield sub_sda_out.eq(1)
        yield dut.read_strb_i.eq(1)
        yield
        yield dut.read_strb_i.eq(0)
        yield from setup()

        yield from wait_for_rstart()

        yield
        byte = yield from read_byte()
        assert byte == (test_addr | 1), f"Expected {test_addr | 1:02X} got {byte:02X}"

        yield from send_ack()
        yield
        yield from write_byte()
        yield from wait_for_main_ack()
        yield from write_byte()
        yield from wait_for_main_nack()
        yield from wait_for_stop()

    def i2c_test_bench():
        yield from write_test_bench()

        for _ in range(100):
            yield

        yield from read_test_bench()
        yield
    sim = Simulator(m)
    sim.add_clock(1/48e6, domain="sync")
    sim.add_sync_process(i2c_test_bench, domain="sync")

    import os; os.makedirs("gtkw", exist_ok=True)
    dutname = f"gtkw/{type(dut).__name__}."
    with sim.write_vcd(dutname+f"vcd"): #, gtkw_file=dutname+f"gtkw", traces=traces):
        sim.run()

if __name__ == "__main__":
    main()