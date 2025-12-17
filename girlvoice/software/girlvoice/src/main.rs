#![no_std]
#![no_main]

use embedded_hal::delay::DelayNs;
use embedded_hal::digital::StatefulOutputPin;
use embedded_hal::i2c::{I2c, SevenBitAddress};
use aw88395::Aw88395;
use sgtl5000::{Sgtl5000};
use sgtl5000::regmap::LineOutBiasCurrent;
use riscv_rt::entry;
use soc_pac as pac;
// extern crate panic_halt;


use girlvoice_hal as hal;
use hal::hal_io::Write;
mod spi;
mod term;

use hal::i2c::I2c0;

const SYS_CLK_FREQ: u32 = 60_000_000;

// hal::gpio! {
//     DC: pac::LcdCtl,
// }
// hal::gpio! {
//     BL: pac::LcdBl,
// }

// hal::spi! {
//     SPI: (pac::LcdSpi, u8),
// }

// hal::impl_gpio!{
//     Led0: pac::Led0,
// }

hal::impl_timer! {
    DELAY: pac::Timer0,
}

hal::impl_serial! {
    Serial0: pac::Uart0,
}

fn power_on_codec(mut sgtl5000: Sgtl5000<I2c0>) {
    // Analog power up settings
    sgtl5000.power_off_startup_power().unwrap();
    sgtl5000.enable_int_osc().unwrap();
    sgtl5000.enable_charge_pump().unwrap();
    sgtl5000.set_bias(0x7).unwrap(); // Set bias current to 50% of nominal per data sheet
    sgtl5000.set_analog_gnd(0x04).unwrap(); // Set analog gnd reference voltage to 0.9v (VDDA/2)
    sgtl5000.set_line_out_ana_gnd(0x4).unwrap(); // Set line out analog ref voltage to 0.9v (VDDIO/2)
    sgtl5000.set_line_out_bias_current(LineOutBiasCurrent::MicroAmp360).unwrap(); // Set line out bias current to 0.36mA for 10kOhm + 1.0nF load
    sgtl5000.enable_small_pop().unwrap(); // Minimize pop

    // Note: here datasheet enables short detect for headphone out

    // Digital blocks and IO power on
    sgtl5000.power_on_adc().unwrap();
    sgtl5000.power_on_dac().unwrap();
    sgtl5000.power_on_line_out().unwrap();

    sgtl5000.set_line_out_left_vol(0x5).unwrap();
    sgtl5000.set_line_out_right_vol(0x5).unwrap();
}

use core::panic::PanicInfo;
#[inline(never)]
#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    let mut serial = unsafe {Serial0::summon()};
    let _err = writeln!(serial,"{}",  info.message());
    if let Some(loc) = info.location() {
        let _ = writeln!(serial, "Panic occurred at line: {}, file: {}", loc.line(), loc.file());
    };
    loop {}
}

#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    let mut delay = DELAY::new(peripherals.timer0, SYS_CLK_FREQ);
    let mut serial = Serial0::new(peripherals.uart0);

    // let mut led = Led0::new(peripherals.led0);

    let i2c0 = I2c0::new(peripherals.i2cfifo);

    // writeln!(serial, "\r").unwrap();
    // writeln!(serial, "Starting main loop!\r").unwrap();
    let mut amp = Aw88395::new(i2c0);


    // write!(serial, "[girlvoice (^O^)~] ").unwrap();

    // let mut term = term::Terminal::new(serial);

    loop {

        // term.handle_char();
        let amp_id = amp.read_id_code();
        match amp_id {
            Ok(id) => writeln!(serial, "Amp IDCODE: {:#x}\r", id).unwrap(),
            Err(e) => writeln!(serial, "read reg failed :<\r").unwrap()
        }

        // led.toggle().unwrap();
        // delay.delay_ms(1000);
    }
}
