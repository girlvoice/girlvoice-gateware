
#![no_std]
pub mod regmap;

use regmap::{LineOutBiasCurrent, MclkFreqSetting, Register, SampleRateSetting, Sgtl5000Config};
use embedded_hal::i2c::{Error, ErrorKind, I2c};

use crate::regmap::{ AdcSource, DataSource};

pub const SGTL5000_QFN20_ADDR: u8 = 0x0A;

pub struct Sgtl5000<'a, I2C: I2c> {
    i2c: &'a mut I2C,
    config: Sgtl5000Config,
}

#[derive(Debug)]
pub enum Sgtl5000Error {
    I2cNack,
    OpFailed,
    InvalidParam,
}

impl<'a, I2C: I2c> Sgtl5000<'a, I2C> {
    pub fn new(i2c: &'a mut I2C) -> Self {
        let config = Sgtl5000Config::default();
        Self { i2c, config }
    }

    /// Consume the device and release the i2c device
    // pub fn release(self) -> I2C {
        // self.i2c
    // }

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
        self.config.chip_ana_power.vag_powerup = true;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn power_off_line_out(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.lineout_powerup = false;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn power_on_adc(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.adc_powerup = true;
        self.config.chip_dig_power.adc_powerup = true;
        self.update_config(Register::ChipAnaPower)?;
        self.update_config(Register::ChipDigPower)
    }

    pub fn power_off_adc(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.adc_powerup = false;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn power_on_dac(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.dac_powerup = true;
        self.config.chip_dig_power.dac_powerup = true;
        self.update_config(Register::ChipAnaPower)?;
        self.update_config(Register::ChipDigPower)
    }

    pub fn power_off_dac(&mut self) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.dac_powerup = false;
        self.config.chip_dig_power.dac_powerup = false;
        self.update_config(Register::ChipAnaPower)?;
        self.update_config(Register::ChipDigPower)
    }

    pub fn set_adc_power(&mut self, power_on: bool) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.adc_powerup = power_on;
        self.config.chip_dig_power.adc_powerup = power_on;
        self.update_config(Register::ChipAnaPower)?;
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
        if bias_code > 0x7 {
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

    pub fn set_line_out_right_vol(&mut self, vol_code: u8) -> Result<(), Sgtl5000Error> {
        self.config.chip_line_out_vol.lo_vol_right = vol_code;
        self.update_config(Register::ChipLineOutVol)
    }

    pub fn set_line_out_left_vol(&mut self, vol_code: u8) -> Result<(), Sgtl5000Error> {
        self.config.chip_line_out_vol.lo_vol_left = vol_code;
        self.update_config(Register::ChipLineOutVol)
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

    pub fn set_mclk_config(&mut self, freq_setting: MclkFreqSetting) -> Result<(), Sgtl5000Error> {
        self.config.chip_clk_ctrl.mclk_freq = freq_setting as u8;
        self.update_config(Register::ChipClkCtrl)
    }

    pub fn set_sample_rate(&mut self, fs_setting: SampleRateSetting) -> Result<(), Sgtl5000Error> {
        self.config.chip_clk_ctrl.sys_fs = fs_setting as u8;
        self.update_config(Register::ChipClkCtrl)
    }

    pub fn set_i2s_controller(&mut self, is_controller: bool) -> Result<(), Sgtl5000Error> {
        self.config.chip_i2s_ctrl.ms = is_controller;
        self.update_config(Register::ChipI2SCtrl)
    }

    // Set the source of data for the I2S output
    pub fn set_i2s_output_source(&mut self, i2s_source: DataSource) -> Result<(), Sgtl5000Error> {
        self.config.chip_sss_ctrl.set_i2s_select(i2s_source as u8);
        self.update_config(Register::ChipSSSCtrl)
    }

    // Set the audio input for the on-chip DAC
    pub fn set_dac_source(&mut self, dac_source: DataSource) -> Result<(), Sgtl5000Error> {
        self.config.chip_sss_ctrl.set_dac_select(dac_source as u8);
        self.update_config(Register::ChipSSSCtrl)
    }

    // Set the audio input for the on-chip ADC
    pub fn set_adc_source(&mut self, adc_source: AdcSource) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_ctrl.set_adc_select((adc_source as u8) == 1);
        self.update_config(Register::ChipAnaCtrl)
    }

    pub fn set_i2s_output_enabled(&mut self, is_enabled: bool) -> Result<(), Sgtl5000Error> {
        self.config.chip_dig_power.i2s_out_powerup = is_enabled;
        self.update_config(Register::ChipDigPower)
    }

    pub fn set_i2s_input_enabled(&mut self, is_enabled: bool) -> Result<(), Sgtl5000Error> {
        self.config.chip_dig_power.i2s_in_powerup = is_enabled;
        self.update_config(Register::ChipDigPower)

    }

    pub fn set_dac_mute(&mut self, mute_left: bool, mute_right: bool) -> Result<(), Sgtl5000Error> {
        self.config.chip_adc_dac_ctrl.set_dac_mute_left(mute_left);
        self.config.chip_adc_dac_ctrl.set_dac_mute_right(mute_right);
        self.update_config(Register::ChipAdcDacCtrl)
    }

    pub fn set_adc_mute(&mut self, mute_enable: bool) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_ctrl.set_adc_muted(mute_enable);
        self.update_config(Register::ChipAnaCtrl)
    }

    pub fn set_line_out_mute(&mut self, mute_enable: bool) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_ctrl.set_line_out_muted(mute_enable);
        self.update_config(Register::ChipAnaCtrl)
    }

    pub fn set_dac_stereo_enabled(&mut self, enabled: bool) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.dac_mono = enabled;
        self.update_config(Register::ChipAnaPower)
    }

    pub fn set_adc_stereo_enabled(&mut self, enabled: bool) -> Result<(), Sgtl5000Error> {
        self.config.chip_ana_power.adc_mono = enabled;
        self.update_config(Register::ChipAnaPower)
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
                ErrorKind::NoAcknowledge(_) => Err(Sgtl5000Error::I2cNack),
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
                ErrorKind::NoAcknowledge(_) => Err(Sgtl5000Error::I2cNack),
                _ => Err(Sgtl5000Error::OpFailed),
            },
            Ok(_) => Ok(((regbuf[0] as u16) << 8) | (regbuf[1] as u16))
        }
    }
}