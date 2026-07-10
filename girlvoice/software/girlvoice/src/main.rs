#![no_std]
#![no_main]

use embedded_hal::delay::DelayNs;
use embedded_hal::spi::SpiDevice;
use aw88395::Aw88395;
use embedded_hal::i2c::I2c;
use sgtl5000::{Sgtl5000};
use sgtl5000::regmap::{I2SDataWidth, LineOutBiasCurrent, MclkFreqSetting, SampleRateSetting};
use riscv_rt::entry;
use soc_pac as pac;

use mipidsi::interface::SpiInterface;
use mipidsi::{Builder, models::GC9A01, options::ColorInversion, TestImage};

use embedded_graphics::{
    mono_font::{ascii::FONT_6X10, MonoTextStyle},
    pixelcolor::Rgb565,
    prelude::*,
    primitives::{
        Circle, PrimitiveStyle, PrimitiveStyleBuilder, Rectangle, StrokeAlignment, Triangle,
    },
    text::{Alignment, Text},
};

use girlvoice_hal as hal;
use hal::hal_io::Write;
mod term;
mod err;


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

fn power_on_codec(sgtl5000: &mut Sgtl5000<I2c0>) -> Result<(), err::Error> {
    // Analog power up settings
    sgtl5000.power_off_startup_power()?;
    sgtl5000.enable_int_osc()?;
    sgtl5000.enable_charge_pump()?;
    sgtl5000.set_bias(0x7)?; // Set bias current to 50% of nominal per data sheet
    sgtl5000.set_analog_gnd(0x04)?; // Set analog gnd reference voltage to 0.9v (VDDA/2)
    sgtl5000.set_line_out_ana_gnd(0x4)?; // Set line out analog ref voltage to 0.9v (VDDIO/2)
    sgtl5000.set_line_out_bias_current(LineOutBiasCurrent::MicroAmp360)?; // Set line out bias current to 0.36mA for 10kOhm + 1.0nF load
    sgtl5000.enable_small_pop()?; // Minimize pop

    // Note: here datasheet enables short detect for headphone out

    // Digital blocks and IO power on
    sgtl5000.power_on_adc()?;
    sgtl5000.power_on_dac()?;
    sgtl5000.power_on_line_out()?;

    sgtl5000.set_line_out_left_vol(0xF)?;
    sgtl5000.set_line_out_right_vol(0x5)?;

    sgtl5000.set_sample_rate(SampleRateSetting::kHz48)?;
    sgtl5000.set_mclk_config(MclkFreqSetting::Fs512)?;
    sgtl5000.set_i2s_controller(false)?;
    sgtl5000.set_i2s_sample_width(I2SDataWidth::Bits16)?;

    sgtl5000.set_dac_stereo_enabled(false)?;
    sgtl5000.set_adc_stereo_enabled(false)?;

    sgtl5000.set_dac_source(sgtl5000::regmap::DataSource::I2sIn)?;
    sgtl5000.set_adc_source(sgtl5000::regmap::AdcSource::LineIn)?;

    sgtl5000.set_dac_mute(false, false)?;
    sgtl5000.set_adc_mute(false)?;
    sgtl5000.set_line_out_mute(false)?;

    sgtl5000.set_i2s_output_enabled(true)?;
    sgtl5000.set_i2s_input_enabled(true)?;
    sgtl5000.set_i2s_output_source(sgtl5000::regmap::DataSource::Adc)?;
    return Ok(())
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

    // This should be a part of the PAC but wishbone memory resource locations are not
    // properly included in the SVD generation yet
    const SPI_FIFO_ADDR: usize = 0xc0000000;
    let spi0 = Spi0::new(peripherals.spiflash_ctrl, SPI_FIFO_ADDR);

    let mut buffer = [0_u8; 1024];
    let interface = SpiInterface::new(spi0, gpo1, &mut buffer);

    let mut display = Builder::new(GC9A01, interface)
        .display_size(240, 240)
        .invert_colors(ColorInversion::Inverted)
        .init(&mut delay).unwrap();


    display.clear(Rgb565::BLACK).unwrap();


    // // Create styles used by the drawing operations.
    // let thin_stroke = PrimitiveStyle::with_stroke(Rgb565::GREEN, 2);
    // let thick_stroke = PrimitiveStyle::with_stroke(Rgb565::CSS_CRIMSON, 3);
    // let border_stroke = PrimitiveStyleBuilder::new()
    //     .stroke_color(Rgb565::CSS_AQUA)
    //     .stroke_width(3)
    //     .stroke_alignment(StrokeAlignment::Inside)
    //     .build();
    // let fill = PrimitiveStyle::with_fill(Rgb565::BLUE);
    // let character_style = MonoTextStyle::new(&FONT_6X10, Rgb565::CSS_PINK);

    // let yoffset = 50;

    // Draw a 3px wide outline around the display.
    // display
    //     .bounding_box()
    //     .into_styled(border_stroke)
    //     .draw(&mut display).unwrap();

    // Draw a triangle.
    // Triangle::new(
    //     Point::new(16, 16 + yoffset),
    //     Point::new(16 + 16, 16 + yoffset),
    //     Point::new(16 + 8, yoffset),
    // )
    // .into_styled(thin_stroke)
    // .draw(&mut display).unwrap();

    //  // Draw centered text.
    // let text = "girlvoice!";
    // Text::with_alignment(
    //     text,
    //     display.bounding_box().center() + Point::new(0, 15),
    //     character_style,
    //     Alignment::Center,
    // )
    // .draw(&mut display).unwrap();


    // display.flush().ok();


    // let mut led = Led0::new(peripherals.led0);

    let mut i2c0 = I2c0::new(peripherals.i2cfifo);

    let mut codec = Sgtl5000::new(&mut i2c0);
    match power_on_codec(&mut codec) {
        Ok(_) => writeln!(serial, "Codec power on success\r").unwrap(),
        Err(e) => writeln!(serial, "Failed to power on codec: {e:?}\r").unwrap(),
    }


    let amp = Aw88395::new(i2c0);

    write!(serial, "[girlvoice (^O^)~] ").unwrap();

    let mut term = term::Terminal::new(serial, amp, delay);

    let img = TestImage::new();
    img.draw(&mut display).unwrap();
    loop {
        img.draw(&mut display).unwrap();
        term.handle_char();
    }
}
