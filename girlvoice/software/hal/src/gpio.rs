use embedded_hal;

#[derive(Debug)]
pub enum GpioError {}

impl embedded_hal::digital::Error for GpioError {
    fn kind(&self) -> embedded_hal::digital::ErrorKind {
        embedded_hal::digital::ErrorKind::Other
    }
}

pub enum PinMode {
    InputOnly = 0b00,
    PushPull = 0b01,
    OpenDrain = 0b10,
    Alternative = 0b11
}

/**
 * Expects a GPIO peripheral with a single pin.
 * TODO: gracefully handle GPIO peripherals with multiple pins
*/
#[macro_export]
macro_rules! impl_gpio {
    ($(
        $GPIOX:ident: $PACGPIOX:ty,
    )+) => {
        $(
            pub struct $GPIOX {
                registers: $PACGPIOX,
                pin_state: bool,
            }

            impl $GPIOX {
                pub fn new(registers: $PACGPIOX) -> Self {
                    registers.mode().write(|w| unsafe {w.pin_0().bits($crate::gpio::PinMode::PushPull as u8)});
                    let pin_state: bool = registers.input().read().pin_0().bit();
                    Self { registers, pin_state}
                }

                pub fn free(self) -> $PACGPIOX {
                    self.registers
                }
            }
            impl $crate::hal::digital::ErrorType for $GPIOX {
                type Error = $crate::gpio::GpioError;
            }

            impl $crate::hal::digital::OutputPin for $GPIOX {
                fn set_low(&mut self) -> Result<(), Self::Error> {
                    self.registers.output().write(|w| w.pin_0().bit(false));
                    self.pin_state = false;
                    return Ok(());
                }

                fn set_high(&mut self) -> Result<(), Self::Error> {
                    self.registers.output().write(|w| w.pin_0().bit(true));
                    self.pin_state = true;
                    return Ok(());
                }
            }

            impl $crate::hal::digital::StatefulOutputPin for $GPIOX {
                fn is_set_high(&mut self) -> Result<bool, Self::Error> {
                    return Ok(self.pin_state)
                }
                fn is_set_low(&mut self) -> Result<bool, Self::Error> {
                    return Ok(!self.pin_state)
                }
            }
        )+

}
}