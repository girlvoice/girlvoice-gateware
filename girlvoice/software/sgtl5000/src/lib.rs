
#![no_std]
mod regmap;

use regmap::{Sgtl5000Config, MappedRegister, Register};
use embedded_hal::i2c::{Error, ErrorKind, I2c};

pub const SGTL5000_QFN20_ADDR: u8 = 0x0A;

pub struct Sgtl5000<I2C> {
    i2c: I2C,
    config: Sgtl5000Config,
}

pub enum Sgtl5000Error {
    OpFailed
}

impl<I2C: I2c> Sgtl5000<I2C> {
    pub fn new(i2c: I2C) -> Self {
        let config = Sgtl5000Config::default();
        Self { i2c, config }
    }

    /// Consume the device and release the i2c device
    pub fn release(self) -> I2C {
        self.i2c
    }

    fn write_reg(&mut self, reg: Register, value: u16) -> Result<(), Sgtl5000Error> {
        let value_bytes = value.to_be_bytes();
        let reg_bytes = reg.addr().to_be_bytes();
        let regbuf = [reg_bytes[0], reg_bytes[1], value_bytes[0], value_bytes[1]];
        match self.i2c.write(SGTL5000_QFN20_ADDR, &regbuf) {
            Err(e) => match e.kind() {
                ErrorKind::NoAcknowledge(_) => Err(Sgtl5000Error::OpFailed),
                _ => Err(Sgtl5000Error::OpFailed),
            },
            Ok(_) => Ok(())
        }
    }

    fn read_reg(&mut self, reg: Register) -> Result<u16, Sgtl5000Error> {
        let mut regbuf = [0u8; 2];
        let reg_bytes = reg.addr().to_be_bytes();
        match self.i2c.write_read(SGTL5000_QFN20_ADDR, &[reg_bytes[0], reg_bytes[1]], &mut regbuf) {
            Err(e) => match e.kind() {
                ErrorKind::NoAcknowledge(_) => Err(Sgtl5000Error::OpFailed),
                _ => Err(Sgtl5000Error::OpFailed),
            },
            Ok(_) => Ok(((regbuf[0] as u16) << 8) | (regbuf[1] as u16))
        }
    }
}