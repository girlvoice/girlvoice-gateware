#![no_std]
#![no_main]

use embedded_hal::delay::DelayNs;
use aw88395::Aw88395;
use embedded_hal::spi::SpiDevice;
use sgtl5000::{Sgtl5000};
use sgtl5000::regmap::LineOutBiasCurrent;
use riscv_rt::entry;
use soc_pac as pac;

use gc9a01::{prelude::*, Gc9a01, SPIDisplayInterface};


use embedded_graphics::{
    mono_font::{ascii::FONT_6X10, MonoTextStyle},
    pixelcolor::BinaryColor,
    pixelcolor::Rgb565,
    prelude::*,
    primitives::{
        Circle, PrimitiveStyle, PrimitiveStyleBuilder, Rectangle, StrokeAlignment, Triangle,
    },
    text::{Alignment, Text},
};

use girlvoice_hal as hal;
use hal::hal_io::Write;
mod spi;
mod term;

use hal::i2c::I2c0;

const SYS_CLK_FREQ: u32 = 60_000_000;

hal::impl_gpio!{
    Gpo1: pac::Gpo1,
}

hal::impl_spi!{
    Spi0: (pac::SpiflashCtrl, u8, 8),
}

hal::impl_gpio!{
    Led0: pac::Led0,
}

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
    let _ = writeln!(serial,"{}",  info.message());
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

    peripherals.gpo1.mode().write(|w| unsafe { w.pin_1().bits(0x1)});
    peripherals.gpo1.output().write(|w| w.pin_1().bit(true));
    let gpo1 = Gpo1::new(peripherals.gpo1);

    let spi0 = Spi0::new(peripherals.spiflash_ctrl);
    // let tx_buf: [u8; 2] =[0xBE, 0xD0];
    // let _ = spi0.write(&tx_buf);

    let interface = SPIDisplayInterface::new(spi0, gpo1);


    // let _ = interface.send_commands(DataFormat::U8(&tx_buf));

    let mut display = Gc9a01::new(
        interface,
        DisplayResolution240x240,
        DisplayRotation::Rotate0
    ).into_buffered_graphics();

    display.init(&mut delay).ok();

    display.clear();

    display.flush().ok();

    // display.fill(0x2d26);


    // Create styles used by the drawing operations.
    let thin_stroke = PrimitiveStyle::with_stroke(Rgb565::GREEN, 2);
    let thick_stroke = PrimitiveStyle::with_stroke(Rgb565::CSS_CRIMSON, 3);
    let border_stroke = PrimitiveStyleBuilder::new()
        .stroke_color(Rgb565::CSS_AQUA)
        .stroke_width(3)
        .stroke_alignment(StrokeAlignment::Inside)
        .build();
    let fill = PrimitiveStyle::with_fill(Rgb565::BLUE);
    let character_style = MonoTextStyle::new(&FONT_6X10, Rgb565::CSS_PINK);

    let yoffset = 20;

    // Draw a 3px wide outline around the display.
    display
        .bounding_box()
        .into_styled(border_stroke)
        .draw(&mut display).unwrap();

    // Draw a triangle.
    Triangle::new(
        Point::new(16, 16 + yoffset),
        Point::new(16 + 16, 16 + yoffset),
        Point::new(16 + 8, yoffset),
    )
    .into_styled(thin_stroke)
    .draw(&mut display).unwrap();

     // Draw centered text.
    let text = "girlvoice!";
    Text::with_alignment(
        text,
        display.bounding_box().center() + Point::new(0, 15),
        character_style,
        Alignment::Center,
    )
    .draw(&mut display).unwrap();


    display.flush().ok();


    // let mut led = Led0::new(peripherals.led0);

    let i2c0 = I2c0::new(peripherals.i2cfifo);

    let amp = Aw88395::new(i2c0);

    write!(serial, "[girlvoice (^O^)~] ").unwrap();

    let mut term = term::Terminal::new(serial, amp, delay);

    loop {
        term.handle_char();
    }
}
