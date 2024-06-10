#![no_std]
#![no_main]

use hex;
use hal::hal::blocking::serial::Write;
use litex_pac as pac;
use riscv_rt::entry;
extern crate panic_halt;

mod timer;
mod i2c_fifo;

use i2c_fifo::I2CFIFO;
use timer::Timer;

use litex_hal as hal;

const SYS_CLK_FREQ: u32 = 75_000_000;

hal::uart ! {
    UART: pac::Uart,
}


#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();
    // let mut led = Leds::new(peripherals.led_gpio);
    let mut timer = Timer::new(peripherals.timer0);

    // let i2c_freq = HertzU32::from_raw(400_000);
    let mut i2c0 = I2CFIFO::new(peripherals.i2cfifo);

    let mut serial = UART {
        registers: peripherals.uart,
    };

    serial.bwrite_all(b"Starting I2C read!\n").unwrap();

    let max_reg_addr: u16 = 0x013a;
    let mut hex_bytes = [0_u8; 2 * 2];

    for addr in (0..max_reg_addr + 1).step_by(2){
        hex::encode_to_slice(addr.to_be_bytes(), &mut hex_bytes).unwrap();
        serial.bwrite_all(b"0x").unwrap();
        serial.bwrite_all(&hex_bytes).unwrap();
        serial.bwrite_all(b": ").unwrap();

        let reg_data = i2c0.read_u16(0x0a, addr);
        hex::encode_to_slice(reg_data.to_be_bytes(), &mut hex_bytes).unwrap();

        serial.bwrite_all(b"0x").unwrap();
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