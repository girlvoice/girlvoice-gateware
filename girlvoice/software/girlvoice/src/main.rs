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
    sgtl5000.enable_charge_pump().unwrap();
    sgtl5000.enable_charge_pump().unwrap();
    sgtl5000.set_bias(0x7).unwrap();
    sgtl5000.set_analog_gnd(0x04).unwrap();
    sgtl5000.set_line_out_ana_gnd(0x4).unwrap();
    sgtl5000.set_line_out_bias_current(LineOutBiasCurrent::MicroAmp360).unwrap();
    sgtl5000.enable_small_pop().unwrap();

    // Digital blocks and IO power on
    sgtl5000.power_on_adc().unwrap();
    sgtl5000.power_on_dac().unwrap();
    sgtl5000.power_on_line_out().unwrap();
}


#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    let mut serial = UART {
        registers: peripherals.uart,
    };

    // let lcd_spi = SPI{
    //     registers: peripherals.lcd_spi
    // };

    let mut delay = DELAY {
        registers: peripherals.timer0,
        sys_clk: SYS_CLK_FREQ
    };

    // let dc = DC { index: 0 }; // LCD Data/Command GPIO
    // let mut bl = BL { index: 0 }; // LCD Backlight GPIO

    // bl.set_high().unwrap();

    // let interface = SPIDisplayInterface::new(lcd_spi, dc);

    // let i2c_freq = HertzU32::from_raw(400_000);
    let mut i2c0 = I2c0::new(peripherals.i2cfifo);

    // let mut display_driver = Gc9a01::new(
    //     interface,
    //     DisplayResolution240x240,
    //     gc9a01::prelude::DisplayRotation::Rotate0
    // );

    // display_driver.init(&mut delay).unwrap();


    // display_driver.set_invert_pixels(true).unwrap();

    // display_driver.clear_fit().unwrap();

    // embedded-graphics hello world

    // Triangle::new(Point::new(32, 16), Point::new(16, 48), Point::new(48, 48))
    // .into_styled(PrimitiveStyle::with_stroke(Rgb565::MAGENTA, 1))
    // .draw(&mut display_driver).unwrap();

    // let pix: [u16; 100] = [Rgb565::MAGENTA.into_storage(); 100];

    // display_driver.set_pixels((100, 100), (110, 110), &mut pix.into_iter()).unwrap();


    serial.write_all(b"Starting I2C read!\n").unwrap();

    // let test = TxCmd::RestartCount.value();
    // let mut test_hex = [0_u8; 2];
    // hex::encode_to_slice(test.to_be_bytes(), &mut test_hex).unwrap();
    // serial.write_all(b"0x").unwrap();
    // serial.write_all(&test_hex).unwrap();
    // serial.write_all(b"\n").unwrap();

    let dev_addr: SevenBitAddress = 0x34;
    let max_reg_addr: u8 = 0x61;
    const BYTES_TO_READ: usize = 2;
    const REG_WIDTH: usize = 1;
    let mut read_buf = [0_u8; BYTES_TO_READ];
    let mut hex_bytes = [0_u8; BYTES_TO_READ * 2];

    let mut reg_hex = [0_u8; REG_WIDTH * 2];



    // i2c0.write(dev_addr, &[0x00, 0x55, 0xaa]).unwrap();

    // let reg_addr: u16 = 0x0002;
    // for reg_addr in (0..max_reg_addr+1).step_by(1) {

    //     hex::encode_to_slice(reg_addr.to_be_bytes(), &mut reg_hex).unwrap();
    //     serial.write_all(b"0x").unwrap();
    //     serial.write_all(&reg_hex).unwrap();
    //     serial.write_all(b": ").unwrap();

    //     i2c0.write_read(dev_addr, &reg_addr.to_be_bytes(), &mut read_buf).unwrap();

    //     serial.write_all(b"0x").unwrap();
    //     hex::encode_to_slice(read_buf, &mut hex_bytes).unwrap();

    //     serial.write_all(&hex_bytes).unwrap();
    //     serial.write_all(b"\n").unwrap();

    //     msleep(&mut timer, 1)
    // }

    // i2c0.write(dev_addr, &[0x04, 0x53, 0x06]).unwrap();
    // // i2c0.write(dev_addr, &[0x52, 0x1f, 0x08]).unwrap();

    // msleep(&mut timer, 2000);
    // i2c0.write(dev_addr, &[0x04, 0x53, 0x04]).unwrap();
    // msleep(&mut timer, 2000);



    // hex::encode_to_slice(reg_addr.to_be_bytes(), &mut reg_hex).unwrap();
    // serial.write_all(b"0x").unwrap();
    // serial.write_all(&reg_hex).unwrap();
    // serial.write_all(b": ").unwrap();

    // i2c0.write_read(dev_addr, &reg_addr.to_be_bytes(), &mut read_buf).unwrap();
    // let mut config = amp.get_sysctrl_bits().unwrap();
    // hex::encode_to_slice(config.to_be_bytes(), &mut config_hex).unwrap();
    // serial.write_all(b"0x").unwrap();
    // serial.write_all(&config_hex).unwrap();
    // serial.write_all(b"\n").unwrap();

    // serial.write_all(b"0x").unwrap();
    // hex::encode_to_slice(read_buf, &mut hex_bytes).unwrap();

    // serial.write_all(&hex_bytes).unwrap();
    // serial.write_all(b"\n").unwrap();

    let mut amp = Aw88395::new(i2c0);

    let mut config_hex = [0u8; 4];

    amp.soft_reset().unwrap();

    let mut config = amp.get_sysctrl_bits().unwrap();
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
        // led.toggle();
        // i2c0.setup_bus(8, true);
        // i2c0.clear();
        delay.delay_ms(1000);
    }
}
