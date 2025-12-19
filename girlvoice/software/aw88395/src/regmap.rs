// Register map and defaults definitions
#[derive(Copy, Clone)]
pub enum Register {
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

pub trait MappedRegister {
    fn value(&self) -> u16;
    fn update(&mut self, val: u16);
}

pub struct SysCtrl {
    // From LSB to MSB
    pub pwdn: bool,
    pub amppd: bool,
    pub dspby: bool,
    pub ipll: bool,
    pub bckinv: bool,
    pub wsinv: bool,
    pub i2sen: bool,
    pub rcv_mode: bool,
    pub mute: bool,
    pub hdcce: bool,
    pub hagce: bool,
    pub rmse: bool,
}

pub struct SysCtrl2 {
    intn: bool,
    intmode: bool,
    pub vol_fine: u8,
    pub vol_course: u8,
}

impl MappedRegister for SysCtrl {
    fn value(&self) -> u16 {
        const RESERVED: u16 = 0x5;
        let mut val: u16 = RESERVED;

        val = (val << 1) | (self.rmse as u16);
        val = (val << 1) | (self.hagce as u16);
        val = (val << 1) | (self.hdcce as u16);
        val = (val << 1) | (self.mute as u16);
        val = (val << 1) | (self.rcv_mode as u16);
        val = (val << 1) | (self.i2sen as u16);
        val = (val << 1) | (self.wsinv as u16);
        val = (val << 1) | (self.bckinv as u16);
        val = (val << 1) | (self.ipll as u16);
        val = (val << 1) | (self.dspby as u16);
        val = (val << 1) | (self.amppd as u16);
        val = (val << 1) | (self.pwdn as u16);

        val
    }

    fn update(&mut self, val: u16) {
        self.pwdn = (val & 1) == 1;
        self.amppd = (val >> 1) & 1 == 1;
        self.dspby = (val >> 2) & 1 == 1;
        self.ipll = (val >> 3) & 1 == 1;
        self.bckinv = (val >> 4) & 1 == 1;
        self.wsinv = (val >> 5) & 1 == 1;
        self.i2sen = (val >> 6) & 1 == 1;
        self.rcv_mode = (val >> 7) & 1 == 1;
        self.mute = (val >> 8) & 1 == 1;
        self.hdcce = (val >> 9) & 1 == 1;
        self.hagce = (val >> 10) & 1 == 1;
        self.rmse = (val >> 11) & 1 == 1;
    }
}

impl MappedRegister for SysCtrl2 {
    fn value(&self) -> u16 {
        const RESERVED: u16 = 0x9;
        let mut val: u16 = self.vol_course as u16;
        val = (val << 6) | (self.vol_fine as u16);
        val = (val << 1) | (self.intmode as u16);
        val = (val << 1) | (self.intn as u16);
        val = (val << 4) | RESERVED;
        val
    }

    fn update(&mut self, val: u16) {
        self.intn = (val >> 4) & 1 == 1;
        self.intmode = (val >> 5) & 1 == 1;
        self.vol_fine = ((val >> 6) & 0x1f) as u8;
        self.vol_course = ((val >> 12) & 0xf) as u8;
    }
}

impl Default for SysCtrl {

    fn default() -> Self {
        Self {
            pwdn: true,
            amppd: true,
            dspby: true,
            ipll: false,
            bckinv: false,
            wsinv: false,
            i2sen: false,
            rcv_mode: false,
            mute: true,
            hdcce: true,
            hagce: false,
            rmse: false,
        }
    }
}

impl Default for SysCtrl2 {
    fn default() -> Self {
        Self {
            intmode: false,
            intn: false,
            vol_fine: 0,
            vol_course: 0,
        }
    }
}
#[readonly::make]
pub struct SysStat {
    pub plls: bool,
    pub oths: bool,
    pub clip_pres: bool,
    pub ocds: bool,
    pub clks: bool,
    pub noclks: bool,
    pub wds: bool,
    pub clips: bool,
    pub sws: bool,
    pub bsts: bool,
    pub ovps: bool,
    pub bstocs: bool,
    pub adps: bool,
    pub uvls: bool,
}

impl MappedRegister for SysStat {
    fn update(&mut self, val: u16) {
        self.plls = (val & 1) == 1;
        self.oths = (val >> 1) & 1 == 1;
        self.clip_pres = (val >> 2) & 1 == 1;
        self.ocds = (val >> 3) & 1 == 1;
        self.clks = (val >> 4) & 1 == 1;
        self.noclks = (val >> 5) & 1 == 1;
        self.wds = (val >> 6) & 1 == 1;
        self.clips = (val >> 7) & 1 == 1;
        self.sws = (val >> 8) & 1 == 1;
        self.bsts = (val >> 9) & 1 == 1;
        self.ovps = (val >> 10) & 1 == 1;
        self.bstocs = (val >> 11) & 1 == 1;
        // Bit 12 Reserved
        self.adps = (val >> 13) & 1 == 1;
        self.uvls = (val >> 14) & 1 == 1;
    }

    fn value(&self) -> u16 {
        let mut val: u16 = 0;
        val = (val << 1) | self.uvls as u16;
        val = (val << 1) | self.adps as u16;
        val = (val << 1) | 0; // Reserved
        val = (val << 1) | self.bstocs as u16;
        val = (val << 1) | self.ovps as u16;
        val = (val << 1) | self.bsts as u16;
        val = (val << 1) | self.sws as u16;
        val = (val << 1) | self.clips as u16;
        val = (val << 1) | self.wds as u16;
        val = (val << 1) | self.noclks as u16;
        val = (val << 1) | self.clks as u16;
        val = (val << 1) | self.ocds as u16;
        val = (val << 1) | self.clip_pres as u16;
        val = (val << 1) | self.oths as u16;
        val = (val << 1) | self.plls as u16;
        val
    }
}

impl Default for SysStat {
    fn default() -> Self {
        Self {
            plls: false,
            oths: false,
            clip_pres: false,
            ocds: false,
            clks: false,
            noclks: false,
            wds: false,
            clips: false,
            sws: false,
            bsts: false,
            ovps: false,
            bstocs: false,
            adps: false,
            uvls: false,
        }
    }

}

pub struct I2SCtrl {
    pub i2ssr: u8,
    pub i2sbck: u8,
    pub i2sfs: u8,
    pub i2smd: u8,
    pub chsel: u8,
    pub slot_num: u8,
}

impl MappedRegister for I2SCtrl {
    fn update(&mut self, val: u16) {
        self.i2ssr = (val & 0xf) as u8;
        self.i2sbck = ((val >> 4) & 0x3) as u8;
        self.i2sfs = ((val >> 6) & 0x3) as u8;
        self.i2smd = ((val >> 8) & 0x3) as u8;
        self.chsel = ((val >> 10) & 0x3) as u8;
        self.slot_num = ((val >> 12) & 0x7) as u8;
    }

    fn value(&self) -> u16 {
        let mut val: u16 = self.slot_num as u16;
        val = (val << 2) | self.chsel as u16;
        val = (val << 2) | self.i2smd as u16;
        val = (val << 2) | self.i2sfs as u16;
        val = (val << 2) | self.i2sbck as u16;
        val = (val << 4) | self.i2ssr as u16;
        val
    }
}

impl Default for I2SCtrl {
    fn default() -> Self {
        Self {
            i2ssr: 0x8,
            i2sbck: 0x2,
            i2sfs: 0x3,
            i2smd: 0,
            chsel: 1,
            slot_num: 0,
        }
    }
}

pub struct Aw88395Config {
    pub sys_stat: SysStat,
    pub sys_ctrl: SysCtrl,
    pub sys_ctrl2: SysCtrl2,
    pub i2s_ctrl: I2SCtrl,
}

impl Default for Aw88395Config {
    fn default() -> Self {
        Self {
            sys_stat: SysStat::default(),
            sys_ctrl: SysCtrl::default(),
            sys_ctrl2: SysCtrl2::default(),
            i2s_ctrl: I2SCtrl::default(),
        }
    }
}

impl Aw88395Config {
    pub fn reg_val(&self, reg: Register) -> u16 {
        match reg {
            Register::SysCtrl => self.sys_ctrl.value(),
            Register::SysCtrl2 => self.sys_ctrl2.value(),
            Register::I2SCtrl => self.i2s_ctrl.value(),
            _ => 0,
        }
    }

    pub fn update_reg(&mut self, reg: Register, val: u16) {
        match reg {
            Register::SysCtrl => self.sys_ctrl.update(val),
            Register::SysCtrl2 => self.sys_ctrl2.update(val),
            Register::I2SCtrl => self.i2s_ctrl.update(val),
            _ => (),
        }
    }
}