#![no_std]
#![no_main]

use hal::hal_io::Write;
use riscv_rt::entry;
use soc_pac as pac;
use girlvoice_hal as hal;
extern crate panic_halt;

use mipidsi::interface::SpiInterface;
use mipidsi::{Builder, models::GC9A01, options::ColorInversion};
use embedded_graphics::{
    mono_font::{ascii::FONT_7X13, MonoTextStyle},
    pixelcolor::Rgb565,
    prelude::*,
    text::{Alignment, Text},
};

const SYS_CLK_FREQ: u32 = 60_000_000;
const FW_RAM_BASE: usize = 0x00000000;
const SPI_FLASH_BASE: usize = 0x10000000;
const SPI_FLASH_FW_BASE: usize = 0x10100000;
const FW_SIZE: usize = 0x00030000;

hal::impl_timer! {
    DELAY: pac::Timer0,
}

hal::impl_serial! {
    Serial0: pac::Uart0,
}

hal::impl_gpio!{
    Gpo1: pac::Gpo1,
}

hal::impl_spi!{
    Spi0: (pac::SpiflashCtrl, u8, 8),
}


#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    let mut delay = DELAY::new(peripherals.timer0, SYS_CLK_FREQ);
    let mut serial = Serial0::new(peripherals.uart0);

    peripherals.gpo1.mode().write(|w| unsafe { w.pin_1().bits(0x1)});
    peripherals.gpo1.output().write(|w| w.pin_1().bit(true));
    let gpo1 = Gpo1::new(peripherals.gpo1);

    const SPI_FIFO_ADDR: usize = 0xc0000000;
    let spi0 = Spi0::new(peripherals.spiflash_ctrl, SPI_FIFO_ADDR);

    let mut buffer = [0_u8; 256];
    let interface = SpiInterface::new(spi0, gpo1, &mut buffer);

    let mut display = Builder::new(GC9A01, interface)
        .display_size(240, 240)
        .invert_colors(ColorInversion::Inverted)
        .init(&mut delay).unwrap();

    display.clear(Rgb565::BLACK).unwrap();

    let character_style = MonoTextStyle::new(&FONT_7X13, Rgb565::CSS_WHITE_SMOKE);

    let text = "Loading Application";
    Text::with_alignment(
        text,
        display.bounding_box().center() + Point::new(0, 15),
        character_style,
        Alignment::Center,
    )
    .draw(&mut display).unwrap();

    let loading_bar_y = display.bounding_box().center().y;
    let loading_bar_x_start = 12;
    let loading_bar_x_step = 8;
    let mut next_segment_point = Point::new(loading_bar_x_start, loading_bar_y);


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
        if words_copied % 2048 == 0 {
            Text::with_alignment(
                "=",
                next_segment_point,
                character_style,
                Alignment::Center
            ).draw(&mut display).unwrap();
            next_segment_point.x += loading_bar_x_step;
            let cur_ram_ptr = unsafe { ram_ptr.offset(i) };
            writeln!(serial, "{words_copied}/{fw_size_words} : ( {cur_ram_ptr:?} ) \r").unwrap();
        }
        words_copied += 1;
    }

    display.clear(Rgb565::BLACK).unwrap();
    Text::with_alignment(
        "Done!",
        display.bounding_box().center() + Point::new(0, 15),
        character_style,
        Alignment::Center,
    )
    .draw(&mut display).unwrap();

    writeln!(serial, "Firmware upload complete, beginning execution from {ram_ptr:?}\r").unwrap();

    let fw_fn_ptr: fn() = unsafe { core::mem::transmute(ram_ptr) };

    fw_fn_ptr();
    loop {}
}
