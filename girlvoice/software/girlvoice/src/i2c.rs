use core::arch::asm;
use fugit::{Duration, HertzU32};
use litex_pac::I2c;

use embedded_hal::i2c::{SevenBitAddress};

pub struct I2C {
    registers: I2c,
    sys_clk_per_scl: u32,
}
#[allow(dead_code)]


impl I2C {
    pub fn new(registers: I2c, freq: HertzU32, sys_clk_freq: HertzU32) -> Self {
        Self { registers, sys_clk_per_scl: sys_clk_freq / freq}
    }

    // pub fn write(mut self, addr: SevenBitAddress, bytes: &[u8]) -> Result<(), i2c::Error> {
    // }

    // pub fn read(mut self, addr: SevenBitAddress, buffer: &mut [u8]) {
    //     self.start();


    // }

    pub fn setup(&mut self){
        self.registers.w().write(|w| w.oe().set_bit());
    }

    fn start(&mut self) {
        self.registers.w().write(|w| w.sda().clear_bit());
        self.registers.w().write(|w| w.scl().clear_bit());
    }

    pub fn delay(&mut self) {
        for _ in 0..self.sys_clk_per_scl/2 {
            unsafe { asm!("nop"); }
        }
    }

    pub fn set(&mut self) {
        self.registers.w().write(|w| w.sda().set_bit());
        self.registers.w().write(|w| w.scl().set_bit());
    }

    pub fn clear(&mut self) {
        self.registers.w().write(|w| w.sda().clear_bit());
        self.registers.w().write(|w| w.scl().clear_bit());
    }
    fn read_bit(&mut self) -> bool {
        self.registers.w().write(|w| w.sda().set_bit());
        self.registers.w().write(|w| w.scl().set_bit());
        let bit = self.registers.r().read().sda().bit();
        self.registers.w().write(|w| w.scl().clear_bit());

        bit
    }

    fn write_bit(&mut self, bit: bool) {
        self.registers.w().write(|w| w.scl().clear_bit());
        if bit {
            self.registers.w().write(|w| w.sda().set_bit());
        } else {
            self.registers.w().write(|w| w.sda().clear_bit());
        }
        // self.registers.w().write(|w| w.sda().);
        self.registers.w().write(|w| w.scl().set_bit());
    }

    pub fn setup_bus(&mut self, addr: SevenBitAddress, read: bool){
        for i in 7..0 {
            // let bit = ((addr >> i) & 1) == 1;
            self.write_bit(true);
            self.write_bit(false);
        }
        self.write_bit(read);
    }
}



// macro_rules! hal {
//     ($($I2CX:ident: ($i2cX:ident),)+) => {
//         $(
//             impl<Sda, Scl> I2C<$I2CX, (Sda, Scl)> {
//                 // Configures the I2C peripheral to work in master mode
//                 pub fn $i2cX<F, SystemF>(
//                     i2c: $I2CX,
//                     sda_pin: Sda,
//                     scl_pin: Scl,
//                     freq: F,
//                     resets: &mut RESETS,
//                     system_clock: SystemF) -> Self
//                 where
//                     F: Into<HertzU32>,
//                     Sda: ValidPinSda<$I2CX> + AnyPin<Pull = PullUp>,
//                     Scl: ValidPinScl<$I2CX> + AnyPin<Pull = PullUp>,
//                     SystemF: Into<HertzU32>,
//                 {
//                     let freq = freq.to_Hz();
//                     assert!(freq <= 1_000_000);
//                     assert!(freq > 0);
//                 }
//             }
//         )+
//     }
// }