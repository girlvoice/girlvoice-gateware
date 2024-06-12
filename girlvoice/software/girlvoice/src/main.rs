#![no_std]
#![no_main]

use embedded_hal::i2c::{I2c, SevenBitAddress};
use hex;
use hal::hal::blocking::serial::Write;
use litex_pac as pac;
use riscv_rt::entry;
extern crate panic_halt;

mod timer;
mod i2c;

use i2c::I2c0;
use timer::Timer;

use litex_hal as hal;

const SYS_CLK_FREQ: u32 = 75_000_000;

hal::uart! {
    UART: pac::Uart,
}


#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();
    // let mut led = Leds::new(peripherals.led_gpio);
    let mut timer = Timer::new(peripherals.timer0);

    let mut serial = UART {
        registers: peripherals.uart,
    };

    // let i2c_freq = HertzU32::from_raw(400_000);
    let mut i2c0 = I2c0::new(peripherals.i2cfifo);


    serial.bwrite_all(b"Starting I2C read!\n").unwrap();

    let dev_addr: SevenBitAddress = 0x0a;
    let max_reg_addr: u16 = 0x000c;
    const BYTES_TO_READ: usize = 2;
    const REG_WIDTH: usize = 2;
    let mut read_buf = [0_u8; BYTES_TO_READ];
    let mut hex_bytes = [0_u8; BYTES_TO_READ * 2];

    let mut reg_hex = [0_u8; REG_WIDTH * 2];

    for reg_addr in (0..max_reg_addr+1).step_by(1) {

        hex::encode_to_slice(reg_addr.to_be_bytes(), &mut reg_hex).unwrap();
        serial.bwrite_all(b"0x").unwrap();
        serial.bwrite_all(&reg_hex).unwrap();
        serial.bwrite_all(b": ").unwrap();

        i2c0.write_read(dev_addr, &reg_addr.to_be_bytes(), &mut read_buf).unwrap();

        serial.bwrite_all(b"0x").unwrap();
        hex::encode_to_slice(read_buf, &mut hex_bytes).unwrap();

        serial.bwrite_all(&hex_bytes).unwrap();
        serial.bwrite_all(b"\n").unwrap();
    }

    loop {
        serial.bwrite_all(b"awaw").unwrap();
        // led.toggle();
        // i2c0.setup_bus(8, true);
        msleep(&mut timer, 500);
        // i2c0.clear();
    }
}

fn msleep(timer: &mut Timer, ms: u32) {
    timer.disable();

    timer.reload(0);
    timer.load(SYS_CLK_FREQ / 1_000 * ms);

    timer.enable();

    // Wait until the time has elapsed
    while timer.value() > 0 {}
}