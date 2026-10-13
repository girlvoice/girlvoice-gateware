#![no_std]
#![no_main]

use hal::hal_io::Write;
use riscv_rt::entry;
use soc_pac as pac;
use girlvoice_hal as hal;
extern crate panic_halt;
const SYS_CLK_FREQ: u32 = 60_000_000;
const FW_RAM_BASE: usize = 0x00000000;
const SPI_FLASH_BASE: usize = 0x10000000;
const SPI_FLASH_FW_BASE: usize = 0x10100000;
const FW_SIZE: usize = 0x00030000;

// hal::impl_timer! {
//     DELAY: pac::Timer0,
// }

hal::impl_serial! {
    Serial0: pac::Uart0,
}


#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    // let mut delay = DELAY::new(peripherals.timer0, SYS_CLK_FREQ);
    let mut serial = Serial0::new(peripherals.uart0);

    // read header from firmware, verify some magic number?
    // copy from flash into RAM, maybe a CRC on it?
    // verify CRC,
    // set new stack and reset pointer, jump to program start

    writeln!(serial, "Beginning RAM initialization from flash\r").unwrap();

    let mut words_copied = 0;
    let fw_size_words = FW_SIZE / 4;
    let flash_ptr = SPI_FLASH_FW_BASE as *mut u32;
    let ram_ptr  = FW_RAM_BASE as *mut u32;
    for i in 0..fw_size_words as isize {
        unsafe {
            let word = flash_ptr.offset(i).read_volatile();
            ram_ptr.offset(i).write_volatile(word);
        }
        words_copied += 1;
        if words_copied % 10 == 0 {
            let cur_ram_ptr = unsafe { ram_ptr.offset(i) };
            writeln!(serial, "{words_copied}/{fw_size_words} : ( {cur_ram_ptr:?} ) \r").unwrap();
        }
    }

    writeln!(serial, "Firmware upload complete, beginning execution from {ram_ptr:?}\r").unwrap();

    let fw_fn_ptr: fn() = unsafe { core::mem::transmute(ram_ptr) };

    fw_fn_ptr();
    loop {

    }
}
