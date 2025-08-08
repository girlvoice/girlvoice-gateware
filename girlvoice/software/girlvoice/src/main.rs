#![no_std]
#![no_main]

use core::fmt::Write;

use embedded_hal::{digital::OutputPin, i2c::{I2c, SevenBitAddress}};
use embedded_hal::delay::DelayNs;
// use gc9a01::{mode::DisplayConfiguration, prelude::DisplayResolution240x240, Gc9a01, SPIDisplayInterface};
use hex;
use soc_pac as pac;
use aw88395::Aw88395;
use riscv_rt::entry;
extern crate panic_halt;

// use embedded_graphics::{
//     pixelcolor::Rgb565,
//     prelude::*,
//     primitives::{
//         PrimitiveStyle, Triangle,
//     },
// };

use girlvoice_hal as hal;
mod spi;

// use i2c::I2c0;

use sgtl5000::Sgtl5000;
use sgtl5000::regmap::LineOutBiasCurrent;

const SYS_CLK_FREQ: u32 = 60_000_000;

// hal::uart! {
//     UART: pac::Uart,
// }

// hal::gpio! {
//     DC: pac::LcdCtl,
// }
// hal::gpio! {
//     BL: pac::LcdBl,
// }

// hal::spi! {
//     SPI: (pac::LcdSpi, u8),
// }

hal::impl_timer! {
    DELAY: pac::Timer0,
}

hal::impl_serial! {
    Serial0: pac::Uart0,
}



// fn power_on_codec(mut sgtl5000: Sgtl5000<I2c0>) {
//     // Analog power up settings
//     sgtl5000.power_off_startup_power().unwrap();
//     sgtl5000.enable_int_osc().unwrap();
//     sgtl5000.enable_charge_pump().unwrap();
//     sgtl5000.set_bias(0x7).unwrap(); // Set bias current to 50% of nominal per data sheet
//     sgtl5000.set_analog_gnd(0x04).unwrap(); // Set analog gnd reference voltage to 0.9v (VDDA/2)
//     sgtl5000.set_line_out_ana_gnd(0x4).unwrap(); // Set line out analog ref voltage to 0.9v (VDDIO/2)
//     sgtl5000.set_line_out_bias_current(LineOutBiasCurrent::MicroAmp360).unwrap(); // Set line out bias current to 0.36mA for 10kOhm + 1.0nF load
//     sgtl5000.enable_small_pop().unwrap(); // Minimize pop

//     // Note: here datasheet enables short detect for headphone out

//     // Digital blocks and IO power on
//     sgtl5000.power_on_adc().unwrap();
//     sgtl5000.power_on_dac().unwrap();
//     sgtl5000.power_on_line_out().unwrap();

//     sgtl5000.set_line_out_left_vol(0x5).unwrap();
//     sgtl5000.set_line_out_right_vol(0x5).unwrap();
// }


#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    let mut delay = DELAY::new(peripherals.timer0, SYS_CLK_FREQ);
    let mut serial = Serial0::new(peripherals.uart0);

    let pac_led = peripherals.led0;

    unsafe {
        pac_led.mode().write( |w| w.bits(0b01));
    }
    loop {
        writeln!(serial, "awawawa").unwrap();
        pac_led.output().write( |w| w.pin_0().bit(true));
        // led.toggle();
        // i2c0.setup_bus(8, true);
        // i2c0.clear();
        delay.delay_ms(1000);
        writeln!(serial, "awawawa").unwrap();
        pac_led.output().write( |w| w.pin_0().bit(false));
        delay.delay_ms(1000);
    }
}
