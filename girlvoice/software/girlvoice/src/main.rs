#![no_std]
#![no_main]

use aw88395::Aw88395;
use embedded_hal::delay::DelayNs;
use sgtl5000::Sgtl5000;
use sgtl5000::regmap::LineOutBiasCurrent;
use riscv_rt::entry;
use soc_pac as pac;

use mipidsi::interface::SpiInterface;
use mipidsi::{Builder, models::GC9A01, options::ColorInversion};

use embedded_graphics::{
    pixelcolor::Rgb565,
    pixelcolor::raw::BigEndian,
    prelude::*,
    framebuffer::{Framebuffer, buffer_size},
};

// display size
const DISPLAY_WIDTH: usize = 240;
const DISPLAY_HEIGHT: usize = 240;

use girlvoice_hal as hal;
use hal::hal_io::Write;
mod term;
mod ui;

use hal::i2c::I2c0;
use ui::math::{Fixed, fx_to_f32};
use ui::ModeKind;

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

    let mut spi_buffer = [0_u8; 512];
    let interface = SpiInterface::new(spi0, gpo1, &mut spi_buffer);

    let mut display = Builder::new(GC9A01, interface)
        .display_size(240, 240)
        .invert_colors(ColorInversion::Inverted)
        .init(&mut delay).unwrap();

    display.clear(Rgb565::BLACK).unwrap();

    // create the local framebuffer
    let mut fb = Framebuffer::<
        Rgb565,
        _,
        BigEndian,
        DISPLAY_WIDTH,
        DISPLAY_HEIGHT,
        { buffer_size::<Rgb565>(DISPLAY_WIDTH, DISPLAY_HEIGHT) }
    >::new();

    // create the visualizer with 12 channels
    let mut visualizer = ui::Visualizer::new(12);

    // envelope energies from vocoder
    let mut energies = [Fixed::ZERO; 12];
    // f32 copy for visualizer (which expects f32)
    let mut energies_f32 = [0.0f32; 12];
    let mut frame_counter: u32 = 0;

    // access envelope registers
    let envelope = &peripherals.envelope;


    // let mut led = Led0::new(peripherals.led0);

    let i2c0 = I2c0::new(peripherals.i2cfifo);

    let amp = Aw88395::new(i2c0);

    write!(serial, "[girlvoice (^O^)~] ").unwrap();

    let mut term = term::Terminal::new(serial, amp, delay);

    // ~10 fps, delay based for now
    const FRAME_DELAY_MS: u32 = 100;
    // switch visualizer every 5 seconds (50 frames at 10fps)
    const MODE_SWITCH_FRAMES: u32 = 50;

    let dt = Fixed::from_num(FRAME_DELAY_MS) / Fixed::from_num(1000);

    // AGC state
    let mut agc_gain = Fixed::ONE;
    let agc_target: Fixed = Fixed::from_num(7) / Fixed::from_num(10);  // 0.7
    let agc_min_gain = Fixed::ONE;
    let agc_max_gain = Fixed::from_num(32);
    let agc_attack = Fixed::from_num(2);
    let agc_release: Fixed = Fixed::from_num(3) / Fixed::from_num(10);  // 0.3
    let agc_threshold_low = agc_target >> 1;

    loop {
        //term.handle_char();

        frame_counter = frame_counter.wrapping_add(1);

        // switch visualizer mode every 5 seconds
        if frame_counter % MODE_SWITCH_FRAMES == 0 {
            let new_mode = match visualizer.current_mode() {
                ModeKind::BarMeter => ModeKind::HarmonicLoop,
                ModeKind::HarmonicLoop => ModeKind::BarMeter,
            };
            visualizer.set_mode(new_mode);
        }

        // read envelope values from hardware registers
        energies[0] = Fixed::ZERO; // ch0 disabled - something wrong with this channel
        energies[1] = Fixed::from_bits(envelope.ch1().read().value().bits() as i32);
        energies[2] = Fixed::from_bits(envelope.ch2().read().value().bits() as i32);
        energies[3] = Fixed::from_bits(envelope.ch3().read().value().bits() as i32);
        energies[4] = Fixed::from_bits(envelope.ch4().read().value().bits() as i32);
        energies[5] = Fixed::from_bits(envelope.ch5().read().value().bits() as i32);
        energies[6] = Fixed::from_bits(envelope.ch6().read().value().bits() as i32);
        energies[7] = Fixed::from_bits(envelope.ch7().read().value().bits() as i32);
        energies[8] = Fixed::from_bits(envelope.ch8().read().value().bits() as i32);
        energies[9] = Fixed::from_bits(envelope.ch9().read().value().bits() as i32);
        energies[10] = Fixed::from_bits(envelope.ch10().read().value().bits() as i32);
        energies[11] = Fixed::from_bits(envelope.ch11().read().value().bits() as i32);

        let mut peak = Fixed::ZERO;
        for e in energies.iter() {
            if *e > peak {
                peak = *e;
            }
        }

        let current_output = peak.saturating_mul(agc_gain);
        if current_output > agc_target {
            // decrease gain
            let delta = agc_attack.saturating_mul(dt).saturating_mul(current_output.saturating_sub(agc_target));
            agc_gain = agc_gain.saturating_sub(delta);
        } else if current_output < agc_threshold_low {
            // increase gain
            let delta = agc_release.saturating_mul(dt);
            agc_gain = agc_gain.saturating_add(delta);
        }
        // clamp gain to valid range
        if agc_gain < agc_min_gain {
            agc_gain = agc_min_gain;
        }
        if agc_gain > agc_max_gain {
            agc_gain = agc_max_gain;
        }

        for (i, e) in energies.iter().enumerate() {
            let scaled = e.saturating_mul(agc_gain).min(Fixed::ONE);
            energies_f32[i] = fx_to_f32(scaled);
        }

        // update visualizer - fade for HarmonicLoop, clear for BarMeter
        match visualizer.current_mode() {
            ModeKind::HarmonicLoop => fade_framebuffer(fb.data_mut()),
            ModeKind::BarMeter => {
                for byte in fb.data_mut().iter_mut() {
                    *byte = 0;
                }
            }
        }

        visualizer.update(fx_to_f32(dt), &energies_f32);

        // render visualizer to our local framebuffer
        visualizer.render(|x, y, color| {
            fb.set_pixel(
                Point::new(x as i32, y as i32),
                Rgb565::new(color.r >> 3, color.g >> 2, color.b >> 3),
            );
        });

        // write framebuffer to display using mipidsi's set_pixels
        let pixels = fb.data().chunks_exact(2).map(|chunk| {
            let raw = ((chunk[0] as u16) << 8) | (chunk[1] as u16);
            Rgb565::from(embedded_graphics::pixelcolor::raw::RawU16::new(raw))
        });
        display.set_pixels(0, 0, DISPLAY_WIDTH as u16 - 1, DISPLAY_HEIGHT as u16 - 1, pixels).ok();

        //term.delay_ms(FRAME_DELAY_MS);
    }
}

// fade all pixels in the framebuffer by multiplying each channel by 7/8
#[inline(always)]
fn fade_framebuffer(data: &mut [u8]) {
    for chunk in data.chunks_exact_mut(2) {
        let pixel = ((chunk[0] as u16) << 8) | (chunk[1] as u16);

        // extract channels
        let r = (pixel >> 11) & 0x1F;
        let g = (pixel >> 5) & 0x3F;
        let b = pixel & 0x1F;

        // multiply by 7/8: (x * 7) >> 3
        let r_faded = (r * 7) >> 3;
        let g_faded = (g * 7) >> 3;
        let b_faded = (b * 7) >> 3;

        let faded = (r_faded << 11) | (g_faded << 5) | b_faded;
        chunk[0] = (faded >> 8) as u8;
        chunk[1] = faded as u8;
    }
}