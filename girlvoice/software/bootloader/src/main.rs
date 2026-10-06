#![no_std]
#![no_main]

use riscv_rt::entry;
use soc_pac as pac;
use girlvoice_hal as hal;
extern crate panic_halt;
const SYS_CLK_FREQ: u32 = 60_000_000;

hal::impl_timer! {
    DELAY: pac::Timer0,
}

hal::impl_serial! {
    Serial0: pac::Uart0,
}


#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    let mut delay = DELAY::new(peripherals.timer0, SYS_CLK_FREQ);
    let mut serial = Serial0::new(peripherals.uart0);
    loop {

    }
}
