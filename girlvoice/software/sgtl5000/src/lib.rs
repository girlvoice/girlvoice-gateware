
#![no_std]
pub mod regmap;

use regmap::{LineOutBiasCurrent, Register, Sgtl5000Config};
use embedded_hal::i2c::{Error, ErrorKind, I2c};

pub const SGTL5000_QFN20_ADDR: u8 = 0x0A;

pub struct Sgtl5000<I2C> {
    i2c: I2C,
    config: Sgtl5000Config,
}

#[derive(Debug)]
pub enum Sgtl5000Error {
    OpFailed,
    InvalidParam,
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

    pub fn power_off_startup_power(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.linereg_simple_powerup = false;
        self.config.chip_ana_power.startup_powerup = false;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn enable_charge_pump(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.vddc_chrgpmp_powerup = true;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn disable_charge_pump(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.vddc_chrgpmp_powerup = false;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn power_on_line_out(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.lineout_powerup = true;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn power_off_line_out(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.lineout_powerup = false;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn power_on_adc(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.adc_powerup = true;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn power_off_adc(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.adc_powerup = false;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn power_on_dac(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.dac_powerup = true;
        self.config.chip_dig_power.dac_powerup = true;
        self.update_config(Register::ChipAnaPower).unwrap();
        self.update_config(Register::ChipDigPower)
    }

    pub fn power_off_dac(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.dac_powerup = false;
        self.config.chip_dig_power.dac_powerup = false;
        self.update_config(Register::ChipAnaPower).unwrap();
        self.update_config(Register::ChipDigPower)
    }

    pub fn enable_int_osc(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_clk_top_ctrl.enable_int_osc = true;
        self.update_config(Register::ChipClkTopCtrl)
    }

    pub fn disable_int_osc(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_clk_top_ctrl.enable_int_osc = false;
        self.update_config(Register::ChipClkTopCtrl)
    }

    pub fn set_analog_gnd(&mut self, voltage_code: u8) -> Result<(), Sgtl5000Error> {
        if voltage_code > 0x1F {
            return Err(Sgtl5000Error::InvalidParam);
        }
        self.config.chip_ref_ctrl.vag_val = voltage_code;
        self.update_config(Register::ChipRefCtrl)
    }

    pub fn set_bias(&mut self, bias_code: u8) -> Result<(), Sgtl5000Error> {
        if bias_code > 0x5 {
            return Err(Sgtl5000Error::InvalidParam);
        }
        self.config.chip_ref_ctrl.bias_ctrl = bias_code;
        self.update_config(Register::ChipRefCtrl)
    }

    pub fn enable_small_pop(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ref_ctrl.small_pop = true;
        self.update_config(Register::ChipRefCtrl)
    }

    pub fn disable_small_pop(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ref_ctrl.small_pop = false;
        self.update_config(Register::ChipRefCtrl)
    }

    pub fn set_line_out_ana_gnd(&mut self, voltage_code: u8) -> Result<(), Sgtl5000Error> {
        if voltage_code > 0x23 {
            return Err(Sgtl5000Error::InvalidParam);
        }
        self.config.chip_line_out_ctrl.lo_vag_cntrl = voltage_code;
        self.update_config(Register::ChipLineOutCtrl)
    }

    pub fn set_line_out_bias_current(&mut self, bias_current: LineOutBiasCurrent) -> Result<(), Sgtl5000Error> {
        match bias_current {
            LineOutBiasCurrent::MicroAmp180 => self.config.chip_line_out_ctrl.out_current = 0x0,
            LineOutBiasCurrent::MicroAmp270 => self.config.chip_line_out_ctrl.out_current = 0x1,
            LineOutBiasCurrent::MicroAmp360 => self.config.chip_line_out_ctrl.out_current = 0x3,
            LineOutBiasCurrent::MicroAmp450 => self.config.chip_line_out_ctrl.out_current = 0x7,
            LineOutBiasCurrent::MicroAmp540 => self.config.chip_line_out_ctrl.out_current = 0xF,
        }
        self.update_config(Register::ChipLineOutCtrl)
    }

    fn update_config(&mut self, reg: Register) -> Result<(), Sgtl5000Error> {
        let reg_val = self.config.reg_val(reg);
        self.write_reg(reg, reg_val)
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