
#[derive(Copy, Clone)]
pub enum Register {
    Id = 0x00,
    ChipAnaPower = 0x0030,

}

impl Register {
    pub fn addr(self) -> u16 {
        match self {
            Register::Id => 0x000,
            Register::ChipAnaPower => 0x0030,
        }
    }
}

pub trait MappedRegister {
    fn value(&self) -> u16;
    fn update(&mut self, val: u16);
}

pub struct ChipAnaPower {
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

pub struct Sgtl5000Config {
    pub chip_ana_power: ChipAnaPower,
}

impl Default for Sgtl5000Config {
    fn default() -> Self {
        Self {
            chip_ana_power: ChipAnaPower::default(),
        }
    }
}

impl Sgtl5000Config {
    pub fn reg_val(&self, reg: Register) -> u16 {
        match reg {
            Register::ChipAnaPower => self.chip_ana_power.value(),
            _ => 0,
        }
    }

    pub fn update_reg(&mut self, reg: Register, val: u16) {
        match reg {
            Register::ChipAnaPower => self.chip_ana_power.update(val),
            _ => (),
        }
    }
}