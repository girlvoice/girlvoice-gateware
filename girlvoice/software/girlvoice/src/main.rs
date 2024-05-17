#![no_std]
#![no_main]

use litex_pac;
use riscv_rt::entry;

mod print;

const SYS_CLK_FREQ: u32 = 75_000_000;

#[entry]
fn main() -> ! {
    let peripherals = litex_pac::Peripherals::take().unwrap();
    print::print_hardware::set_hardware(peripherals.uart);

    loop {

    }
}
