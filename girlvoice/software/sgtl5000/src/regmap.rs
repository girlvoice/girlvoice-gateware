
use bitfield::bitfield;
use bitfield::{BitRange, BitRangeMut};


#[derive(Copy, Clone)]
pub enum Register {
    Id = 0x00,
    ChipDigPower = 0x0002,
    ChipClkCtrl = 0x0004,
    ChipI2SCtrl = 0x0006,
    ChipSSSCtrl = 0x000A,
    ChipAdcDacCtrl = 0x000E,
    ChipDacVol = 0x0010,
    ChipAnaAdcCtrl = 0x0020,
    ChipAnaCtrl = 0x0024,
    ChipRefCtrl = 0x0028,
    ChipLineOutCtrl = 0x002C,
    ChipLineOutVol = 0x002E,
    ChipAnaPower = 0x0030,
    ChipClkTopCtrl = 0x0034,
}

impl Register {
    pub fn addr(self) -> u16 {
        return self as u16;
    }
}

pub trait MappedRegister {
    fn value(&self) -> u16;
    fn update(&mut self, val: u16);
}

// ChipRefPower -----------------------
pub struct ChipDigPower {
    // LSB First
    pub i2s_in_powerup: bool,
    pub i2s_out_powerup: bool,
    pub dap_powerup: bool,
    pub dac_powerup: bool,
    pub adc_powerup: bool,
}

impl MappedRegister for ChipDigPower {
    fn value(&self) -> u16 {
        let mut val: u16 = self.adc_powerup as u16;
        val = (val << 1) | (self.dac_powerup as u16);
        val = (val << 1) | (self.dap_powerup as u16);
        val = (val << 3) | (self.i2s_out_powerup as u16);
        val = (val << 1) | (self.i2s_in_powerup as u16);
        val
    }

    fn update(&mut self, val: u16) {
        self.i2s_in_powerup = (val & 0x1) == 1;
        self.i2s_out_powerup = (val & 0x2) == 1;
        self.dap_powerup = (val & 0x10) == 1;
        self.dac_powerup = (val & 0x20) == 1;
        self.adc_powerup = (val & 0x40) == 1;
    }
}

impl Default for ChipDigPower {
    fn default() -> Self {
        Self {
            i2s_in_powerup: false,
            i2s_out_powerup: false,
            dap_powerup: false,
            dac_powerup: false,
            adc_powerup: false
        }
    }
}

// ChipClkCtrl
pub struct ChipClkCtrl {
    pub mclk_freq: u8,
    pub sys_fs: u8,
    pub rate_mode: u8,
}

impl MappedRegister for ChipClkCtrl {
    fn value(&self) -> u16 {
        let mut val = self.rate_mode as u16;
        val = (val << 2) | (self.sys_fs as u16);
        val = (val << 2) | (self.mclk_freq as u16);
        val
    }

    fn update(&mut self, val: u16) {
        self.mclk_freq = (val & 0x3) as u8;
        self.sys_fs = ((val >> 2) & 0x3) as u8;
        self.rate_mode = ((val >> 4) &0x3) as u8;
    }
}

impl Default for ChipClkCtrl {
    fn default() -> Self {
        Self {
            mclk_freq: 0,
            sys_fs: 0x2,
            rate_mode: 0,
        }
    }
}

// ChipI2SCtrl
pub struct ChipI2SCtrl {
    // LSB first
    pub lrpol: bool,
    pub lralign: bool,
    pub i2s_mode: u8,
    pub dlen: u8,
    pub sclk_inv: bool,
    pub ms: bool,
    pub sclkfreq: bool,
}

pub enum I2SDataWidth {
    Bits32 = 0x0,
    Bits24 = 0x1,
    Bits20 = 0x2,
    Bits16 = 0x3
}

pub enum I2SFormatSetting {
    I2SLeftJustified = 0x0,
    RightJustified = 0x1,
    PCM = 0x2,
}

impl MappedRegister for ChipI2SCtrl {
    fn value(&self) -> u16 {
        let mut val = self.sclkfreq as u16;
        val = (val << 1) | (self.ms as u16);
        val = (val << 1) | (self.sclk_inv as u16);
        val = (val << 2) | (self.dlen as u16);
        val = (val << 2) | (self.i2s_mode as u16);
        val = (val << 1) | (self.lralign as u16);
        val = (val << 1) | (self.lrpol as u16);
        val
    }

    fn update(&mut self, val: u16) {
        self.lrpol = (val & 0x1) == 1;
        self.lralign = ((val >> 1) & 0x1) == 1;
        self.i2s_mode = ((val >> 2) & 0b11) as u8;
        self.dlen = ((val >> 4) & 0b11) as u8;
        self.sclk_inv = ((val >> 6) & 0b1) == 1;
        self.ms = ((val >> 7) & 0b1) == 1;
        self.sclkfreq = ((val >> 8) & 0b1) == 1;
    }
}

impl Default for ChipI2SCtrl {
    fn default() -> Self {
        Self {
            lrpol: false,
            lralign: false,
            i2s_mode: 0b00,
            dlen: 0b01,
            sclk_inv: false,
            ms: false,
            sclkfreq: false,
        }
    }
}

pub enum DataSource {
    Adc = 0x0,
    I2sIn = 0x1,
    Dap = 0x3,
}

impl TryFrom<u8> for DataSource {
    type Error = ();
    fn try_from(value: u8) -> Result<Self, Self::Error> {
        const ADC_VAL: u8 = DataSource::Adc as u8;
        const I2S_VAL: u8 = DataSource::I2sIn as u8;
        const DAP_VAL: u8 = DataSource::Dap as u8;
        match value {
            ADC_VAL => Ok(DataSource::Adc),
            I2S_VAL => Ok(DataSource::I2sIn),
            DAP_VAL => Ok(DataSource::Dap),
            _ => Err(())
        }
    }
}

bitfield!{
    pub struct ChipSSSCtrl(u16);
    u8;
    pub i2s_select, set_i2s_select: 1, 0;
    pub dac_select, set_dac_select: 5, 4;
    pub dap_select, set_dap_select: 7, 6;
    pub dap_mix_select, set_dap_mix_select: 9, 8;
    pub dac_lrswap, set_dac_lrswap: 12;
    pub dap_lrswap, set_dap_lrswap: 13;
    pub dap_mix_lrswap, set_dap_mix_lrswap: 14;
}

impl MappedRegister for ChipSSSCtrl {
    fn value(&self) -> u16 {
        self.bit_range(15, 0)
    }

    fn update(&mut self, val: u16) {
        self.set_bit_range(15, 0, val)
    }
}

impl Default for ChipSSSCtrl {
    fn default() -> Self {
        Self(0x0010)
    }
}

bitfield!{
    pub struct ChipAdcDacCtrl(u16);
    bool;
    pub adc_hpf_bypass, set_adc_hpf_bypassed: 0;
    pub adc_hpf_freeze, set_adc_hpf_frozen: 1;
    pub is_dac_left_muted, set_dac_mute_left: 2;
    pub is_dac_right_muted, set_dac_mute_right: 3;
    pub vol_expo_ramp, set_vol_expo_ramp: 8;
    pub is_vol_ramp_enabled, set_vol_ramp_enabled: 9;
    pub is_vol_busy_dac_left, _: 12;
    pub is_vol_busy_dac_right, _: 13;
}

impl MappedRegister for ChipAdcDacCtrl {
    fn value(&self) -> u16 {
        self.bit_range(15, 0)
    }

    fn update(&mut self, val: u16) {
        self.set_bit_range(15, 0, val)
    }
}

impl Default for ChipAdcDacCtrl {
    fn default() -> Self {
        Self(0x020C)
    }
}

bitfield!{
    pub struct ChipDacVol(u16);
    u8;
    pub dac_vol_left, set_dac_vol_left: 7, 0;
    pub dac_vol_right, set_dac_vol_right: 15, 8;
}

impl MappedRegister for ChipDacVol {
    fn value(&self) -> u16 {
        self.bit_range(15, 0)
    }

    fn update(&mut self, val: u16) {
        self.set_bit_range(15, 0, val)
    }
}

impl Default for ChipDacVol {
    fn default() -> Self {
        Self(0x3C3C)
    }
}


// ChipRefPower -----------------------
pub struct ChipRefCtrl {
    // LSB first
    pub small_pop: bool,
    pub bias_ctrl: u8, // 3 bits
    pub vag_val: u8, // 5 bits
}

pub enum MclkFreqSetting {
    Fs256 = 0x0,
    Fs384 = 0x1,
    Fs512 = 0x2,
    PLL   = 0x3
}

pub enum SampleRateSetting {
    kHz32 = 0x0,
    kHz44d1 = 0x1,
    kHz48 = 0x2,
    kHz96 = 0x3,
}

impl MappedRegister for ChipRefCtrl {
    fn value(&self) -> u16 {
        let mut val: u16 = (self.vag_val & 0x1F) as u16;
        val = (val << 3) | ((self.bias_ctrl & 0x7) as u16);
        val = (val << 1 ) | (self.small_pop as u16);
        val
    }
    fn update(&mut self, val: u16) {
        self.small_pop = (val & 0x1) == 1;
        self.bias_ctrl = ((val >> 1) & 0x7) as u8;
        self.vag_val = ((val >> 4) & 0x1f) as u8;
    }
}

impl Default for ChipRefCtrl {
    fn default() -> Self {
        Self {
            small_pop: false,
            bias_ctrl: 0x0,
            vag_val: 0x0
        }
    }
}

// ChipLineOutCtrl --------------------
pub struct ChipLineOutCtrl {
    pub lo_vag_cntrl: u8,
    pub out_current: u8,
}

pub enum LineOutBiasCurrent {
    MicroAmp180 = 0x0,
    MicroAmp270 = 0x1,
    MicroAmp360 = 0x3,
    MicroAmp450 = 0x7,
    MicroAmp540 = 0xF
}

impl MappedRegister for ChipLineOutCtrl {
    fn value(&self) -> u16 {
        let mut val: u16 = ((self.out_current & 0xF) << 2) as u16; // 2 reserved bits
        val = (val << 6) | (self.lo_vag_cntrl & 0x3F) as u16;
        val
    }

    fn update(&mut self, val: u16) {
        self.lo_vag_cntrl = (val & 0x3F) as u8;
        self.out_current = ((val >> 8) & 0xF) as u8;
    }
}

impl Default for ChipLineOutCtrl {
    fn default() -> Self {
        Self {
            lo_vag_cntrl: 0x0,
            out_current: 0x0
        }
    }
}

// ChipLineOutVol
pub struct ChipLineOutVol {
    pub lo_vol_left: u8,
    pub lo_vol_right: u8,
}

impl MappedRegister for ChipLineOutVol {
    fn value(&self) -> u16 {
        let mut val = self.lo_vol_right as u16;
        val = (val << 8) | (self.lo_vol_left as u16);
        val
    }

    fn update(&mut self, val: u16) {
        self.lo_vol_left = (val & 0x1F) as u8;
        self.lo_vol_right = ((val >> 8) & 0x1F) as u8;
    }
}

impl Default for ChipLineOutVol {
    fn default() -> Self {
        Self {
            lo_vol_left: 0x4,
            lo_vol_right: 0x4,
        }
    }
}

// ChipAnaPower -----------------------
pub struct ChipAnaPower {
    // LSB first
    pub lineout_powerup: bool,
    pub adc_powerup: bool,
    pub capless_headphone_powerup: bool,
    pub dac_powerup: bool,
    pub headphone_powerup: bool,
    pub reftop_powerup: bool,
    pub adc_mono: bool,
    pub vag_powerup: bool,
    pub vcoamp_powerup: bool,
    pub linereg_d_powerup: bool,
    pub pll_powerup: bool,
    pub vddc_chrgpmp_powerup: bool,
    pub startup_powerup: bool,
    pub linereg_simple_powerup: bool,
    pub dac_mono: bool,
}

impl MappedRegister for ChipAnaPower {
    fn value(&self) -> u16 {
        const RESERVED: u16 = 0x0;
        let mut val = RESERVED;
        val = (val << 1) | (self.dac_mono as u16);
        val = (val << 1) | (self.linereg_simple_powerup as u16);
        val = (val << 1) | (self.startup_powerup as u16);
        val = (val << 1) | (self.vddc_chrgpmp_powerup as u16);
        val = (val << 1) | (self.pll_powerup as u16);
        val = (val << 1) | (self.linereg_d_powerup as u16);
        val = (val << 1) | (self.vcoamp_powerup as u16);
        val = (val << 1) | (self.vag_powerup as u16);
        val = (val << 1) | (self.adc_mono as u16);
        val = (val << 1) | (self.reftop_powerup as u16);
        val = (val << 1) | (self.headphone_powerup as u16);
        val = (val << 1) | (self.dac_powerup as u16);
        val = (val << 1) | (self.capless_headphone_powerup as u16);
        val = (val << 1) | (self.adc_powerup as u16);
        val = (val << 1) | (self.lineout_powerup as u16);
        val
    }

    fn update(&mut self, val: u16) {
        self.lineout_powerup = (val & 1) == 1;
        self.adc_powerup = (val >> 1) & 1 == 1;
        self.capless_headphone_powerup = (val >> 2) & 1 == 1;
        self.dac_powerup = (val >> 3) & 1 == 1;
        self.headphone_powerup = (val >> 4) & 1 == 1;
        self.reftop_powerup = (val >> 5) & 1 == 1;
        self.adc_mono = (val >> 6) & 1 == 1;
        self.vag_powerup = (val >> 7) & 1 == 1;
        self.vcoamp_powerup = (val >> 8) & 1 == 1;
        self.linereg_d_powerup = (val >> 9) & 1 == 1;
        self.pll_powerup = (val >> 10) & 1 == 1;
        self.vddc_chrgpmp_powerup = (val >> 11) & 1 == 1;
        self.startup_powerup = (val >> 12) & 1 == 1;
        self.linereg_simple_powerup = (val >> 13) & 1 == 1;
        self.dac_mono = (val >> 14) & 1 == 1;
    }
}

impl Default for ChipAnaPower {
    fn default() -> Self {
        Self {
            lineout_powerup: false,
            adc_powerup: false,
            capless_headphone_powerup: false,
            dac_powerup: false,
            headphone_powerup: false,
            reftop_powerup: true,
            adc_mono: true,
            vag_powerup: false,
            vcoamp_powerup: false,
            linereg_d_powerup: false,
            pll_powerup: false,
            vddc_chrgpmp_powerup: false,
            startup_powerup: true,
            linereg_simple_powerup: true,
            dac_mono: true
        }
    }
}

// ChipClkTopCtrl -----------------------
pub struct ChipClkTopCtrl {
    pub input_freq_div2: bool,
    pub enable_int_osc: bool,
}

impl MappedRegister for ChipClkTopCtrl {
    fn value(&self) -> u16 {
        let mut val: u16 = self.enable_int_osc as u16;
        val = (val << 8) | (self.input_freq_div2 as u16);
        val << 3
    }

    fn update(&mut self, val: u16) {
        self.input_freq_div2 = (val >> 3) & 1 == 1;
        self.enable_int_osc = (val >> 11) & 1 == 1;
    }
}

impl Default for ChipClkTopCtrl {
    fn default() -> Self {
        Self {
            input_freq_div2: false,
            enable_int_osc: false,
        }
    }
}

pub struct Sgtl5000Config {
    pub chip_dig_power: ChipDigPower,
    pub chip_clk_ctrl: ChipClkCtrl,
    pub chip_i2s_ctrl: ChipI2SCtrl,
    pub chip_sss_ctrl: ChipSSSCtrl,
    pub chip_adc_dac_ctrl: ChipAdcDacCtrl,
    pub chip_dac_vol: ChipDacVol,
    pub chip_ref_ctrl: ChipRefCtrl,
    pub chip_line_out_ctrl: ChipLineOutCtrl,
    pub chip_line_out_vol: ChipLineOutVol,
    pub chip_ana_power: ChipAnaPower,
    pub chip_clk_top_ctrl: ChipClkTopCtrl,
}

impl Default for Sgtl5000Config {
    fn default() -> Self {
        Self {
            chip_dig_power: ChipDigPower::default(),
            chip_clk_ctrl: ChipClkCtrl::default(),
            chip_i2s_ctrl: ChipI2SCtrl::default(),
            chip_sss_ctrl: ChipSSSCtrl::default(),
            chip_adc_dac_ctrl: ChipAdcDacCtrl::default(),
            chip_dac_vol: ChipDacVol::default(),
            chip_ref_ctrl: ChipRefCtrl::default(),
            chip_line_out_ctrl: ChipLineOutCtrl::default(),
            chip_line_out_vol: ChipLineOutVol::default(),
            chip_ana_power: ChipAnaPower::default(),
            chip_clk_top_ctrl: ChipClkTopCtrl::default(),
        }
    }
}

impl Sgtl5000Config {
    pub fn reg_val(&self, reg: Register) -> u16 {
        match reg {
            Register::ChipDigPower => self.chip_dig_power.value(),
            Register::ChipClkCtrl => self.chip_clk_ctrl.value(),
            Register::ChipI2SCtrl => self.chip_i2s_ctrl.value(),
            Register::ChipRefCtrl => self.chip_ref_ctrl.value(),
            Register::ChipLineOutCtrl => self.chip_line_out_ctrl.value(),
            Register::ChipLineOutVol => self.chip_line_out_vol.value(),
            Register::ChipAnaPower => self.chip_ana_power.value(),
            Register::ChipClkTopCtrl => self.chip_clk_top_ctrl.value(),
            _ => 0,
        }
    }

    pub fn update_reg(&mut self, reg: Register, val: u16) {
        match reg {
            Register::ChipDigPower => self.chip_dig_power.update(val),
            Register::ChipClkCtrl => self.chip_clk_ctrl.update(val),
            Register::ChipI2SCtrl => self.chip_i2s_ctrl.update(val),
            Register::ChipRefCtrl => self.chip_ref_ctrl.update(val),
            Register::ChipLineOutCtrl => self.chip_line_out_ctrl.update(val),
            Register::ChipLineOutVol => self.chip_line_out_vol.update(val),
            Register::ChipAnaPower => self.chip_ana_power.update(val),
            Register::ChipClkTopCtrl => self.chip_clk_top_ctrl.update(val),
            _ => (),
        }
    }
}