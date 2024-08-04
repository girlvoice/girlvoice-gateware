#![no_std]
#![no_main]

use embedded_hal::i2c::{I2c, SevenBitAddress};
use hex;
use hal::hal::blocking::serial::Write;
use litex_pac as pac;
use aw88395::Aw88395;
use riscv_rt::entry;
extern crate panic_halt;

mod timer;
mod i2c;

use i2c::I2c0;
use timer::Timer;
use litex_hal as hal;

const SYS_CLK_FREQ: u32 = 60_000_000;

hal::uart! {
    UART: pac::Uart,
}


#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();
    let mut timer = Timer::new(peripherals.timer0);

    let mut serial = UART {
        registers: peripherals.uart,
    };

    // let i2c_freq = HertzU32::from_raw(400_000);
    let  i2c0 = I2c0::new(peripherals.i2cfifo);

    let mut amp = Aw88395::new(i2c0);

    serial.bwrite_all(b"Starting I2C read!\n").unwrap();

    // let test = TxCmd::RestartCount.value();
    // let mut test_hex = [0_u8; 2];
    // hex::encode_to_slice(test.to_be_bytes(), &mut test_hex).unwrap();
    // serial.bwrite_all(b"0x").unwrap();
    // serial.bwrite_all(&test_hex).unwrap();
    // serial.bwrite_all(b"\n").unwrap();

    // let dev_addr: SevenBitAddress = 0x34;
    // let max_reg_addr: u8 = 0x61;
    // const BYTES_TO_READ: usize = 2;
    // const REG_WIDTH: usize = 1;
    // let mut read_buf = [0_u8; BYTES_TO_READ];
    // let mut hex_bytes = [0_u8; BYTES_TO_READ * 2];

    // let mut reg_hex = [0_u8; REG_WIDTH * 2];

    // i2c0.write(dev_addr, &[0x00, 0x55, 0xaa]).unwrap();

    // let reg_addr: u16 = 0x0002;
    // for reg_addr in (0..max_reg_addr+1).step_by(1) {

    //     hex::encode_to_slice(reg_addr.to_be_bytes(), &mut reg_hex).unwrap();
    //     serial.bwrite_all(b"0x").unwrap();
    //     serial.bwrite_all(&reg_hex).unwrap();
    //     serial.bwrite_all(b": ").unwrap();

    //     i2c0.write_read(dev_addr, &reg_addr.to_be_bytes(), &mut read_buf).unwrap();

    //     serial.bwrite_all(b"0x").unwrap();
    //     hex::encode_to_slice(read_buf, &mut hex_bytes).unwrap();

    //     serial.bwrite_all(&hex_bytes).unwrap();
    //     serial.bwrite_all(b"\n").unwrap();

    //     msleep(&mut timer, 1)
    // }

    // i2c0.write(dev_addr, &[0x04, 0x53, 0x06]).unwrap();
    // // i2c0.write(dev_addr, &[0x52, 0x1f, 0x08]).unwrap();

    // msleep(&mut timer, 2000);
    // i2c0.write(dev_addr, &[0x04, 0x53, 0x04]).unwrap();
    // msleep(&mut timer, 2000);


    // for reg_addr in (0..max_reg_addr+1).step_by(1) {

    //     hex::encode_to_slice(reg_addr.to_be_bytes(), &mut reg_hex).unwrap();
    //     serial.bwrite_all(b"0x").unwrap();
    //     serial.bwrite_all(&reg_hex).unwrap();
    //     serial.bwrite_all(b": ").unwrap();

    //     i2c0.write_read(dev_addr, &reg_addr.to_be_bytes(), &mut read_buf).unwrap();

    //     serial.bwrite_all(b"0x").unwrap();
    //     hex::encode_to_slice(read_buf, &mut hex_bytes).unwrap();

    //     serial.bwrite_all(&hex_bytes).unwrap();
    //     serial.bwrite_all(b"\n").unwrap();

    //     msleep(&mut timer, 1)
    // }

    // hex::encode_to_slice(reg_addr.to_be_bytes(), &mut reg_hex).unwrap();
    // serial.bwrite_all(b"0x").unwrap();
    // serial.bwrite_all(&reg_hex).unwrap();
    // serial.bwrite_all(b": ").unwrap();

    // i2c0.write_read(dev_addr, &reg_addr.to_be_bytes(), &mut read_buf).unwrap();
    // let mut config = amp.get_sysctrl_bits().unwrap();
    // hex::encode_to_slice(config.to_be_bytes(), &mut config_hex).unwrap();
    // serial.bwrite_all(b"0x").unwrap();
    // serial.bwrite_all(&config_hex).unwrap();
    // serial.bwrite_all(b"\n").unwrap();

    // serial.bwrite_all(b"0x").unwrap();
    // hex::encode_to_slice(read_buf, &mut hex_bytes).unwrap();

    // serial.bwrite_all(&hex_bytes).unwrap();
    // serial.bwrite_all(b"\n").unwrap();


    let mut config_hex = [0u8; 4];

    amp.soft_reset().unwrap();

    let mut config = amp.get_sysctrl_bits().unwrap();
    hex::encode_to_slice(config.to_be_bytes(), &mut config_hex).unwrap();
    serial.bwrite_all(b"0x").unwrap();
    serial.bwrite_all(&config_hex).unwrap();
    serial.bwrite_all(b"\n").unwrap();

    serial.bwrite_all(b"Starting amp power-up sequence\n").unwrap();
    serial.bwrite_all(b"Powering on\n").unwrap();
    amp.power_on().unwrap();
    serial.bwrite_all(b"Power on success\n").unwrap();

    msleep(&mut timer, 500);

    config = amp.get_sysctrl_bits().unwrap();
    hex::encode_to_slice(config.to_be_bytes(), &mut config_hex).unwrap();
    serial.bwrite_all(b"0x").unwrap();
    serial.bwrite_all(&config_hex).unwrap();
    serial.bwrite_all(b"\n").unwrap();


    while !amp.pll_locked().unwrap() {
        serial.bwrite_all(b"Waiting for PLL lock...\n").unwrap();


        msleep(&mut timer, 2000);
    }
    serial.bwrite_all(b"PLL Locked\n").unwrap();

    serial.bwrite_all(b"Setting volume to 500 i guess\n").unwrap();
    amp.set_volume(500).unwrap();

    serial.bwrite_all(b"Enabling class D amplifier and boost converter\n").unwrap();
    amp.enable_amp().unwrap();
    serial.bwrite_all(b"Waiting for amplifier power-on...\n").unwrap();

    while !amp.boost_init_finished().unwrap() {
        serial.bwrite_all(b"Waiting for amplifier power-on...\n").unwrap();
        msleep(&mut timer, 2000);
    }
    serial.bwrite_all(b"Amplifier power-on complete\n").unwrap();

    // serial.bwrite_all(b"Unmuting\n").unwrap();
    // amp.unmute().unwrap();

    // serial.bwrite_all(b"Welcome to girlvoice\n").unwrap();
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