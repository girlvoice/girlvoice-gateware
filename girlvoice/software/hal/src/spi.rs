// embedded-hal spi implementation for LCD write-only SPI controller
#[macro_export]
macro_rules! impl_spi {
    ($(
        $SPIX:ident: ($PACSPIX:ty, $WORD:ty, $LENGTH:tt),
    )+) => {
        $(
            #[derive(Debug)]
            pub struct $SPIX {
                registers: $PACSPIX,
            }

            #[derive(Debug, Copy, Clone, Eq, PartialEq)]
            pub enum SpiError {
                TransactionFailed,
                InvalidState,
            }
            impl $crate::hal::spi::Error for SpiError {
                fn kind(&self) -> $crate::hal::spi::ErrorKind {
                    match *self {
                        SpiError::TransactionFailed => $crate::hal::spi::ErrorKind::Other,
                        SpiError::InvalidState => $crate::hal::spi::ErrorKind::Other
                    }
                }
            }

            impl $crate::hal::spi::ErrorType for $SPIX {
                type Error = SpiError;
            }

            impl $SPIX {
                pub fn new(registers: $PACSPIX) -> Self {
                    registers.phy().write(|w| unsafe {
                        w.length().bits($LENGTH);
                        w.width().bits(0x1);
                        w.mask().bits(0x1)
                    });
                    registers.cs().write(|w| w.select().bit(false));
                    Self { registers }
                }

                pub fn free(self) -> $PACSPIX {
                    self.registers
                }

                fn tx_ready(&mut self) -> bool {
                    self.registers.status().read().tx_ready().bit()
                }

                fn read_priv(&mut self, bufs: &mut [$WORD]) ->  Result<(), SpiError> {
                    Err(SpiError::InvalidState)
                }

                fn write_priv(&mut self, words: &[$WORD]) -> Result<(), SpiError> {
                    self.registers.cs().write(|w| w.select().bit(true));
                    let mut words_cleared = 0;
                    for word in words.iter() {
                        while ! self.tx_ready() {}
                        self.registers.data().write(|w| unsafe {w.tx().bits(*word as u32)});
                    }

                    self.registers.cs().write(|w| w.select().bit(false));
                    Ok(())
                }

                fn transfer_priv(&mut self, read: &mut [$WORD], write: &[$WORD]) -> Result<(), SpiError> {
                    Err(SpiError::InvalidState)
                }

                fn transfer_in_place_priv(&mut self, words: &mut [$WORD]) -> Result<(), SpiError> {
                    Err(SpiError::InvalidState)
                }
            }

            impl $crate::hal::spi::SpiDevice<$WORD> for $SPIX {

                fn transaction(&mut self, operations: &mut [$crate::hal::spi::Operation<'_, $WORD>]) -> Result<(), Self::Error> {
                    for op in operations {
                        match op {
                            $crate::hal::spi::Operation::Read(buf) => self.read_priv(buf)?,
                            $crate::hal::spi::Operation::Write(buf) => self.write_priv(buf)?,
                            $crate::hal::spi::Operation::Transfer(read_buf, write_buf) => self.transfer_priv(read_buf, write_buf)?,
                            $crate::hal::spi::Operation::TransferInPlace(buf) => self.transfer_in_place(buf)?,
                            $crate::hal::spi::Operation::DelayNs(_) => continue,
                        }
                    }
                    Ok(())
                }
            }
        )+
    };
}