//! A platform agnostic driver to interface with the AW88395 Smart Amplifier via I2C
//!
//! This driver was built using [`embedded-hal`] traits.

#![no_std]
#![allow(dead_code)]

// use embedded_hal::i2c;

use embedded_hal::i2c::{Error, ErrorKind, I2c};


const AW88395_ADDR: u8 = 0x34;

enum Register {
    Id = 0x00,
    SysStat = 0x01,
    SysInt = 0x02,
    SysIntMask = 0x03,
    SysCtrl = 0x04,
    SysCtrl2 = 0x05,
    I2SCtrl = 0x06,
    I2SCfg1 = 0x07,
    I2SCfg2 = 0x08,
    HAGCCfg1 = 0x09,
    HAGCCfg2 = 0x0a,
    HAGCCfg3 = 0x0b,
    VBat = 0x21,
    Temp = 0x22,
    PVdd = 0x23,
    BstCtrl1 = 0x60,
    BstCtrl2 = 0x61,
}
pub struct Aw88395<I2C> {
    i2c: I2C,
}

pub enum Aw88395Error {
    OpFailed,
}


impl<I2C: I2c> Aw88395<I2C> {
    pub fn new(i2c: I2C) -> Self {
        Self { i2c }
    }

    /// Consume the device and release the i2c device
    pub fn release(self) -> I2C {
        self.i2c
    }

    pub fn power_on(&mut self) -> Result<(), Aw88395Error> {
        self.write_reg(Register::SysCtrl, 0x5306)?;
        Ok(())
    }

    fn write_reg(&mut self, reg: Register, value: u16) -> Result<(), Aw88395Error> {
        let value_bytes = value.to_be_bytes();
        let regbuf = [reg as u8, value_bytes[1], value_bytes[0]];
        match self.i2c.write(AW88395_ADDR, &regbuf) {
            Err(e) => match e.kind() {
                ErrorKind::NoAcknowledge(_) => Err(Aw88395Error::OpFailed),
                _ => Err(Aw88395Error::OpFailed),
            },
            Ok(_) => Ok(())
        }
    }

    fn read_reg(&mut self, reg: Register) -> Result<u16, Aw88395Error> {
        let mut regbuf = [0u8; 2];

        match self.i2c.write_read(AW88395_ADDR, &[reg as u8], &mut regbuf) {
            Err(e) => match e.kind() {
                ErrorKind::NoAcknowledge(_) => Err(Aw88395Error::OpFailed),
                _ => Err(Aw88395Error::OpFailed),
            },
            Ok(_) => Ok(((regbuf[0] as u16) << 1) | (regbuf[1] as u16))
        }

    }
}