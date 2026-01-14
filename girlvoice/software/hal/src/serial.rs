/// Re-export hal serial error type
pub use crate::hal_io::ErrorKind as Error;

#[macro_export]
macro_rules! impl_serial {
    ($(
        $SERIALX:ident: $PACUARTX:ty,
    )+) => {
        $(
            #[derive(Debug)]
            pub struct $SERIALX {
                registers: $PACUARTX,
            }

            // lifecycle
            impl $SERIALX {
                /// Create a new `Serial` from the [`UART`](crate::pac::UART) peripheral.
                pub fn new(registers: $PACUARTX) -> Self {
                    Self { registers }
                }

                /// Release the [`Uart`](crate::pac::UART) peripheral and consume self.
                pub fn free(self) -> $PACUARTX {
                    self.registers
                }

                /// Obtain a static `Serial` instance for use in e.g. interrupt handlers
                ///
                /// # Safety
                ///
                /// 'Tis thine responsibility, that which thou doth summon.
                pub unsafe fn summon() -> Self {
                    Self {
                        registers: <$PACUARTX>::steal(),
                    }
                }
            }

            // trait: From
            impl From<$PACUARTX> for $SERIALX {
                fn from(registers: $PACUARTX) -> $SERIALX {
                    $SERIALX::new(registers)
                }
            }

            // - embedded_hal 1.0 traits --------------------------------------

            impl $crate::hal_io::ErrorType for $SERIALX {
                type Error = $crate::serial::Error;
            }

            // trait: hal_nb::serial::Write
            impl $crate::hal_io::Write for $SERIALX {
                fn write(&mut self, buf: &[u8]) -> Result<usize, Self::Error> {
                    for word in buf.iter() {
                        while !self.registers.tx_ready().read().txe().bit() {}
                        self.registers.tx_data().write(|w| unsafe { w.data().bits(*word) });

                    }
                    Ok(buf.len())
                }

                fn flush(&mut self) -> Result<(), Self::Error> {
                    while self.registers.tx_ready().read().txe().bit() {}
                    Ok(())
                }
            }

            impl $crate::hal_io::Read for $SERIALX {
                fn read(&mut self, buf: &mut [u8]) -> Result<usize, Self::Error> {
                    let mut i = 0;
                    for word in buf.iter_mut() {
                        while !self.registers.rx_avail().read().rxe().bit() {}

                        *word = self.registers.rx_data().read().data().bits();
                        i += 1;
                    }
                    Ok(i)
                }
            }

        )+
    }
}
