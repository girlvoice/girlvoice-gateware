use litex_pac::LedGpio;

pub struct Leds {
    registers: LedGpio,
}

#[allow(dead_code)]
impl Leds {
    pub fn new(registers: LedGpio) -> Self {
        Self { registers }
    }

    pub fn off(&mut self) {
        unsafe {
            self.registers.out().write(|w| w.bits(0x0000_0000));
        }
    }

    pub fn on(&mut self) {
        unsafe {
            self.registers.out().write(|w| w.bits(0xFFFF_FFFF));
        }
    }

    pub fn toggle(&mut self) {
        self.toggle_mask(0xFFFF_FFFF);
    }

    pub fn toggle_mask(&mut self, mask: u32) {
        let val: u32 = self.registers.out().read().bits() ^ mask;
        unsafe {
            self.registers.out().write(|w| w.bits(val));
        }
    }
}