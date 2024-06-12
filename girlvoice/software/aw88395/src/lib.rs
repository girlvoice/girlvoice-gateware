#![no_std]
#![allow(dead_code)]

use embedded_hal::blocking::i2c;

// use embedded_hal::i2c::{I2c, SevenBitAddress};


const ADDR: u8 = 0x34;
pub struct Aw88395<I2C> {
    i2c: I2C,
}

impl<I2C: i2c::I2c<SevenBitAddress>> Aw88395<I2C> {
    pub fn new(i2c: I2C) -> Self {
        Self { i2c }
    }
}