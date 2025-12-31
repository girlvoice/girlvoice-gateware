#![no_std]
#![no_main]

use aw88395::Aw88395;
use sgtl5000::Sgtl5000;
use sgtl5000::regmap::LineOutBiasCurrent;
use riscv_rt::entry;
use soc_pac as pac;

use gc9a01::{prelude::*, Gc9a01, SPIDisplayInterface};

use embedded_graphics::{
    pixelcolor::Rgb565,
    pixelcolor::raw::BigEndian,
    prelude::*,
    framebuffer::{Framebuffer, buffer_size},
};

// Display dimensions
const DISPLAY_WIDTH: usize = 240;
const DISPLAY_HEIGHT: usize = 240;

/// Fade all pixels in the framebuffer by multiplying each channel by ~0.7
/// Uses integer math: channel = channel * 179 / 256
/// The framebuffer is RGB565 big-endian (2 bytes per pixel)
fn fade_framebuffer(data: &mut [u8]) {
    for chunk in data.chunks_exact_mut(2) {
        // Big-endian: first byte is high byte, second is low byte
        let pixel = ((chunk[0] as u16) << 8) | (chunk[1] as u16);

        let r = ((pixel >> 11) & 0x1F) as u32;
        let g = ((pixel >> 5) & 0x3F) as u32;
        let b = (pixel & 0x1F) as u32;

        // Multiply by 179/256 ≈ 0.7
        let r_faded = ((r * 179) >> 8) as u16;
        let g_faded = ((g * 179) >> 8) as u16;
        let b_faded = ((b * 179) >> 8) as u16;

        let faded = (r_faded << 11) | (g_faded << 5) | b_faded;
        chunk[0] = (faded >> 8) as u8;
        chunk[1] = faded as u8;
    }
}

use girlvoice_hal as hal;
use hal::hal_io::Write;
mod term;
mod ui;

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
    let interface = SPIDisplayInterface::new(spi0, gpo1);



    let mut display = Gc9a01::new(
        interface,
        DisplayResolution240x240,
        DisplayRotation::Rotate0
    );

    display.init_with_addr_mode(&mut delay).ok();

    // create the local framebuffer
    // using BigEndian to match the display's expected byte order
    let mut fb = Framebuffer::<
        Rgb565,
        _,
        BigEndian,
        DISPLAY_WIDTH,
        DISPLAY_HEIGHT,
        { buffer_size::<Rgb565>(DISPLAY_WIDTH, DISPLAY_HEIGHT) }
    >::new();

    // create the visualizer with 8 channels (for testing)
    let mut visualizer = ui::Visualizer::new(8);

    // simulated energies for testing (will be replaced with actual vocoder data)
    let mut demo_energies = [0.0f32; 8];
    let mut frame_counter: u32 = 0;


    // let mut led = Led0::new(peripherals.led0);

    let i2c0 = I2c0::new(peripherals.i2cfifo);

    let amp = Aw88395::new(i2c0);

    write!(serial, "[girlvoice (^O^)~] ").unwrap();

    let mut term = term::Terminal::new(serial, amp, delay);

    // ~30 fps, delay based for now
    const FRAME_DELAY_MS: u32 = 33;

    loop {
        term.handle_char();

        // update demo energies with a simple pattern for testing
        frame_counter = frame_counter.wrapping_add(1);
        for i in 0..8 {
            let phase = (frame_counter as f32 / 60.0) + (i as f32 * 0.5);
            demo_energies[i] = (libm::sinf(phase) * 0.5 + 0.5) * 0.8;
        }

        // update visualizer (dt = 1/30 sec)
        visualizer.update(FRAME_DELAY_MS as f32 / 1000.0, &demo_energies);

        fade_framebuffer(fb.data_mut());

        // render visualizer to our local framebuffer
        visualizer.render(|x, y, color| {
            fb.set_pixel(
                Point::new(x as i32, y as i32),
                Rgb565::new(color.r >> 3, color.g >> 2, color.b >> 3),
            );
        });

        // write framebuffer to display
        display.set_draw_area((0, 0), (DISPLAY_WIDTH as u16 - 1, DISPLAY_HEIGHT as u16 - 1)).ok();
        display.draw_buffer(unsafe {
            // reinterpret as [u16] for the display driver
            core::slice::from_raw_parts(
                fb.data().as_ptr() as *const u16,
                DISPLAY_WIDTH * DISPLAY_HEIGHT,
            )
        }).ok();

        term.delay_ms(FRAME_DELAY_MS);
    }
}
