//! A platform agnostic driver to interface with the AW88395 Smart Amplifier via I2C
//!
//! This driver was built using [`embedded-hal`] traits.

#![no_std]
#![allow(dead_code)]

// use embedded_hal::i2c;

mod regmap;
use regmap::{Aw88395Config, MappedRegister, Register};

use embedded_hal::i2c::{Error, ErrorKind, I2c};


const AW88395_ADDR: u8 = 0x34;

pub struct Aw88395<I2C> {
    i2c: I2C,
    config: Aw88395Config,
}

pub enum Aw88395Error {
    OpFailed,
    OutOfRange,
}


impl<I2C: I2c> Aw88395<I2C> {
    pub fn new(i2c: I2C) -> Self {
        let config = Aw88395Config::default();
        Self { i2c, config }
    }

    /// Consume the device and release the i2c device
    pub fn release(self) -> I2C {
        self.i2c
    }

    pub fn power_on(&mut self) -> Result<(), Aw88395Error> {
        self.config.sys_ctrl.pwdn = false;
        self.update_config(Register::SysCtrl)
    }

    pub fn power_off(&mut self) -> Result<(), Aw88395Error> {
        self.config.sys_ctrl.pwdn = true;
        self.update_config(Register::SysCtrl)
    }

    pub fn mute(&mut self) -> Result<(), Aw88395Error> {
        self.config.sys_ctrl.mute = true;
        self.update_config(Register::SysCtrl)
    }

    pub fn unmute(&mut self) -> Result<(), Aw88395Error> {
        self.config.sys_ctrl.mute = false;
        self.update_config(Register::SysCtrl)
    }

    pub fn enable_amp(&mut self) -> Result<(), Aw88395Error> {
        self.config.sys_ctrl.amppd = false;
        self.update_config(Register::SysCtrl)
    }

    pub fn disable_amp(&mut self) -> Result<(), Aw88395Error> {
        self.config.sys_ctrl.amppd = true;
        self.update_config(Register::SysCtrl)
    }

    pub fn set_volume(&mut self, volume: u16) -> Result<(), Aw88395Error> {
        if volume > 0x3ff {
            return Err(Aw88395Error::OutOfRange);
        }
        self.config.sys_ctrl2.vol_course = (volume >> 6) as u8;
        self.config.sys_ctrl2.vol_fine = (volume & 0x3f) as u8;
        self.update_config(Register::SysCtrl2)
    }

    fn update_config(&mut self, reg: Register) -> Result<(), Aw88395Error> {
        let reg_val = self.config.reg_val(reg);
        self.write_reg(reg, reg_val)
    }

    pub fn pll_locked(&mut self) -> Result<bool, Aw88395Error> {
        self.update_status().map(|_| self.config.sys_stat.plls)
    }

    pub fn amp_switching(&mut self) -> Result<bool, Aw88395Error> {
        self.update_status().map(|_| self.config.sys_stat.sws)
    }

    pub fn boost_init_finished(&mut self) -> Result<bool, Aw88395Error> {
        self.update_status().map(|_| self.config.sys_stat.bsts)
    }

    fn update_status(&mut self) -> Result<(), Aw88395Error> {
        self.read_reg(regmap::Register::SysStat).map(|val| self.config.sys_stat.update(val))
    }

    fn write_reg(&mut self, reg: Register, value: u16) -> Result<(), Aw88395Error> {
        let value_bytes = value.to_be_bytes();
        let regbuf = [reg.addr(), value_bytes[1], value_bytes[0]];
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

        match self.i2c.write_read(AW88395_ADDR, &[reg.addr()], &mut regbuf) {
            Err(e) => match e.kind() {
                ErrorKind::NoAcknowledge(_) => Err(Aw88395Error::OpFailed),
                _ => Err(Aw88395Error::OpFailed),
            },
            Ok(_) => Ok(((regbuf[0] as u16) << 1) | (regbuf[1] as u16))
        }

    }
}