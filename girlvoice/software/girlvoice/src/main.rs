#![no_std]
#![no_main]

use embedded_hal::{digital::OutputPin, i2c::{I2c, SevenBitAddress}};
use embedded_io::Write;
use embedded_hal::delay::DelayNs;
// use gc9a01::{mode::DisplayConfiguration, prelude::DisplayResolution240x240, Gc9a01, SPIDisplayInterface};
use hex;
use litex_pac as pac;
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

mod timer;
mod i2c;
mod spi;

use i2c::I2c0;

use litex_hal as hal;
use sgtl5000::Sgtl5000;
use sgtl5000::regmap::LineOutBiasCurrent;

const SYS_CLK_FREQ: u32 = 60_000_000;

hal::uart! {
    UART: pac::Uart,
}

// hal::gpio! {
//     DC: pac::LcdCtl,
// }
// hal::gpio! {
//     BL: pac::LcdBl,
// }

// hal::spi! {
//     SPI: (pac::LcdSpi, u8),
// }

hal::timer! {
    DELAY: pac::Timer0,
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


#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    let mut serial = UART {
        registers: peripherals.uart,
    };

    let mut delay = DELAY {
        registers: peripherals.timer0,
        sys_clk: SYS_CLK_FREQ
    };

    // let i2c_freq = HertzU32::from_raw(400_000);
    let mut i2c0 = I2c0::new(peripherals.i2cfifo);

    let mut amp = Aw88395::new(i2c0);


    amp.soft_reset().unwrap();

    let mut config = amp.get_sysctrl_bits().unwrap();
    let mut config_hex = [0u8; 4];
    hex::encode_to_slice(config.to_be_bytes(), &mut config_hex).unwrap();
    serial.write_all(b"0x").unwrap();
    serial.write_all(&config_hex).unwrap();
    serial.write_all(b"\n").unwrap();

    serial.write_all(b"Starting amp power-up sequence\n").unwrap();
    serial.write_all(b"Enabling I2S Interface\n").unwrap();
    serial.write_all(b"Powering on\n").unwrap();
    amp.power_on().unwrap();
    serial.write_all(b"Power on success\n").unwrap();

    // msleep(&mut timer, 1000);

    config = amp.get_sysctrl_bits().unwrap();
    hex::encode_to_slice(config.to_be_bytes(), &mut config_hex).unwrap();
    serial.write_all(b"0x").unwrap();
    serial.write_all(&config_hex).unwrap();
    serial.write_all(b"\n").unwrap();


    while !amp.pll_locked().unwrap() {
        serial.write_all(b"Waiting for PLL lock...\n").unwrap();
        delay.delay_ms(1000);
    }
    serial.write_all(b"PLL Locked\n").unwrap();

    serial.write_all(b"Setting volume to 500 i guess\n").unwrap();
    amp.set_volume(100).unwrap();
    // amp.set_i2s_channel(aw88395::ChannelSetting::Left).unwrap();
    amp.enable_i2s().unwrap();
    // amp.set_i2s_data_fmt(aw88395::I2SDataFmt::MSBFirst).unwrap();
    // amp.set_i2s_samplerate(0x6).unwrap();
    // amp.set_i2s_data_width(0x0).unwrap();

    serial.write_all(b"Enabling class D amplifier and boost converter\n").unwrap();
    amp.enable_amp().unwrap();
    serial.write_all(b"Waiting for amplifier power-on...\n").unwrap();

    while !amp.boost_init_finished().unwrap() {
        serial.write_all(b"Waiting for amplifier power-on...\n").unwrap();
        delay.delay_ms(1000);
    }
    serial.write_all(b"Amplifier power-on complete\n").unwrap();

    serial.write_all(b"Unmuting\n").unwrap();
    amp.unmute().unwrap();

    i2c0 = amp.release();

    // Dump all amp registers to verify power on sequence was completed.
    let dev_addr: SevenBitAddress = 0x34;
    let max_reg_addr: u8 = 0x61;
    const BYTES_TO_READ: usize = 2;
    const REG_WIDTH: usize = 1;
    let mut read_buf = [0_u8; BYTES_TO_READ];
    let mut hex_bytes = [0_u8; BYTES_TO_READ * 2];
    let mut reg_hex = [0_u8; REG_WIDTH * 2];
    for reg_addr in (0..max_reg_addr+1).step_by(1) {

        hex::encode_to_slice(reg_addr.to_be_bytes(), &mut reg_hex).unwrap();
        serial.write_all(b"0x").unwrap();
        serial.write_all(&reg_hex).unwrap();
        serial.write_all(b": ").unwrap();

        i2c0.write_read(dev_addr, &reg_addr.to_be_bytes(), &mut read_buf).unwrap();

        serial.write_all(b"0x").unwrap();
        hex::encode_to_slice(read_buf, &mut hex_bytes).unwrap();

        serial.write_all(&hex_bytes).unwrap();
        serial.write_all(b"\n").unwrap();

        delay.delay_ms(1);
    }
    serial.write_all(b"Welcome to girlvoice\n").unwrap();
    loop {
        serial.write_all(b"awaw").unwrap();
        delay.delay_ms(1000);
    }
}
