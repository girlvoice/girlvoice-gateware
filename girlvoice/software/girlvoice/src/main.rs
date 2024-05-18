#![no_std]
#![no_main]

// use riscv;
use litex_pac;
use riscv_rt::entry;
extern crate panic_halt;

mod print;
mod timer;
mod led;
use timer::Timer;
use led::Leds;

const SYS_CLK_FREQ: u32 = 75_000_000;

#[entry]
fn main() -> ! {
    let peripherals = litex_pac::Peripherals::take().unwrap();
    print::print_hardware::set_hardware(peripherals.uart);
    let mut led = Leds::new(peripherals.led_gpio);
    let mut timer = Timer::new(peripherals.timer0);

    loop {
        // print!("awaw");
        led.toggle();
        msleep(&mut timer, 500);
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