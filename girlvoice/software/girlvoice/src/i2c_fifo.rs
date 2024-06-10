use core::u8;

use litex_pac::I2cfifo;
use embedded_hal::i2c::SevenBitAddress;

pub struct I2CFIFO {
    registers: I2cfifo,
}

impl I2CFIFO {
    pub fn new(registers: I2cfifo) -> Self {
        Self { registers }
    }

    fn is_read_complete(&mut self) -> bool {
        self.registers.i2cfifosr_msb().read().rdcmpl().bit()
    }

    // TX FIFO can be reset to known-good state by reading from it.
    fn reset_tx_fifo(&mut self) {
        self.registers.i2ctxfifo_lsb().read().bits();
    }

    // RX FIFO can be reset to known-good state by writing anything to it.
    fn reset_rx_fifo(&mut self) {
        self.registers.i2crxfifo_lsb().write(|w| unsafe{ w.bits(0) });
    }

    fn push_tx_byte(&mut self, byte: u8, cmd: u8){
        self.registers.i2ctxfifo_lsb().write(|w| unsafe{ w.txlsb().bits(byte) });
        self.registers.i2ctxfifo_msb().write(|w| unsafe{ w.cmd().bits(cmd)} );
    }


    fn start_tx(&mut self, addr: SevenBitAddress) {
        self.reset_tx_fifo();
        self.push_tx_byte(0, 3);
        self.push_tx_byte(addr << 1, 0);
    }


    fn pop_rx_byte(&mut self) -> u8 {
        let byte = self.registers.i2crxfifo_lsb().read().rx_lsb().bits();
        let _first = self.registers.i2crxfifo_msb().read().dfirst().bit();
        byte
    }

    fn tx_reg16(&mut self, addr: SevenBitAddress, reg: u16) {
        self.start_tx(addr);
        self.push_tx_byte((reg >> 8) as u8, 0);
        self.push_tx_byte(reg as u8, 0);
    }

    pub fn write_u16(&mut self, addr: SevenBitAddress, reg: u16, data: u16) {
        self.tx_reg16(addr, reg);
        self.push_tx_byte((data >> 8) as u8, 0);
        self.push_tx_byte(data as u8, 1);
    }

    pub fn read_u16(&mut self, addr: SevenBitAddress, reg: u16) -> u16 {
        // Setup read transaction
        self.tx_reg16(addr, reg);
        self.push_tx_byte(1, 3); // read 2 bytes
        self.push_tx_byte(addr << 1 | 1, 0);

        while !self.is_read_complete() {}
        let upper = self.pop_rx_byte();
        let lower = self.pop_rx_byte();
        self.reset_rx_fifo();

        ((upper as u16) << 8) | (lower as u16)
    }
}