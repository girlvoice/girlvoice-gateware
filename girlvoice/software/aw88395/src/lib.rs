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

#[derive(Debug, )]
pub enum Aw88395Error {
    OpFailed,
    OutOfRange,
}

pub enum ChannelSetting {
    Left  = 0x1,
    Right = 0x2,
    Mono  = 0x3,
}

pub enum I2SDataFmt {
    Philip   = 0x0,
    MSBFirst = 0x1,
    LSBFirst = 0x2,
}
pub enum SampleRate {
    SR8kHz  = 0x0,
    SR11kHz = 0x1,
    SR12kHz = 0x2,
    SR16kHz = 0x3,
    SR22kHz = 0x4,
    SR24kHz = 0x5,
    SR32kHz = 0x6,
    SR44kHz = 0x7,
    SR48kHz = 0x8,
    SR96kHz = 0x9
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

    pub fn enable_i2s(&mut self) -> Result<(), Aw88395Error> {
        self.config.sys_ctrl.i2sen = true;
        self.update_config(Register::SysCtrl)
    }

    pub fn disable_i2s(&mut self) -> Result<(), Aw88395Error> {
        self.config.sys_ctrl.i2sen = false;
        self.update_config(Register::SysCtrl)
    }

    pub fn set_i2s_channel(&mut self, channel_setting: u8) -> Result<(), Aw88395Error> {
        self.config.i2s_ctrl.chsel = channel_setting;
        self.update_config(Register::I2SCtrl)
    }

    pub fn set_i2s_samplerate(&mut self, sample_rate: u8) -> Result<(), Aw88395Error> {
        self.config.i2s_ctrl.i2ssr = sample_rate;
        self.update_config(Register::I2SCtrl)
    }

    pub fn set_i2s_data_fmt(&mut self, fmt: I2SDataFmt) -> Result<(), Aw88395Error> {
        self.config.i2s_ctrl.i2smd = fmt as u8;
        self.update_config(Register::I2SCtrl)
    }

    pub fn set_i2s_data_width(&mut self, bit_width: u8) -> Result<(), Aw88395Error>{
        self.config.i2s_ctrl.i2sfs = bit_width;
        self.update_config(Register::I2SCtrl)
    }

    pub fn set_volume(&mut self, volume: u16) -> Result<(), Aw88395Error> {
        if volume > 0x3ff {
            return Err(Aw88395Error::OutOfRange);
        }
        self.config.sys_ctrl2.vol_course = (volume >> 6) as u8;
        self.config.sys_ctrl2.vol_fine = (volume & 0x3f) as u8;
        self.update_config(Register::SysCtrl2)
    }

    pub fn enable_hagc(&mut self) -> Result<(), Aw88395Error> {
        self.config.sys_ctrl.hagce = true;
        self.update_config(Register::SysCtrl)
    }

    pub fn disable_hagc(&mut self) -> Result<(), Aw88395Error> {
        self.config.sys_ctrl.hagce = false;
        self.update_config(Register::SysCtrl)
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

    pub fn get_status_bits(&mut self) -> Result<u16, Aw88395Error> {
        self.read_reg(regmap::Register::SysStat)
    }

    pub fn get_sysctrl_bits(&mut self) -> Result<u16, Aw88395Error> {
        self.read_reg(regmap::Register::SysCtrl)
    }

    pub fn get_sysctrl2_bits(&mut self) -> Result<u16, Aw88395Error> {
        self.read_reg(regmap::Register::SysCtrl2)
    }

    pub fn soft_reset(&mut self) -> Result<(), Aw88395Error> {
        self.write_reg(Register::Id, 0x55aa)
    }

    fn write_reg(&mut self, reg: Register, value: u16) -> Result<(), Aw88395Error> {
        let value_bytes = value.to_be_bytes();
        let regbuf = [reg.addr(), value_bytes[0], value_bytes[1]];
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
            Ok(_) => Ok(((regbuf[0] as u16) << 8) | (regbuf[1] as u16))
        }

    }
}