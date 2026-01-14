// embedded-hal spi implementation for LCD write-only SPI controller
#[macro_export]
macro_rules! impl_spi {
    ($(
        $SPIX:ident: ($PACSPIX:ty, $WORD:ty, $LENGTH:tt),
    )+) => {
        $(
            use core::ptr;

            #[derive(Debug)]
            pub struct $SPIX {
                registers: $PACSPIX,
                spi_fifo_ptr: *mut u32
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
                pub fn new(registers: $PACSPIX, fifo_addr: usize) -> Self {
                    registers.phy().write(|w| unsafe {
                        w.length().bits($LENGTH);
                        w.width().bits(0x1);
                        w.mask().bits(0x1)
                    });
                    registers.cs().write(|w| w.select().bit(false));

                    Self { registers , spi_fifo_ptr: fifo_addr as *mut u32}
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
                    self.registers.phy().write(|w| unsafe { w.length().bits(32) });
                    self.registers.cs().write(|w| w.select().bit(true));

                    // Chunk outgoing buffers into 32-bit words to ensure optimal usage of the
                    // 32-bit wide memory bus
                    for chunk in words.chunks(4) {
                        if chunk.len() == 4 {
                            let mut full_word: u32 = 0;
                            for byte in chunk {
                                full_word = full_word << 8;
                                full_word = full_word | *byte as u32;
                            }
                            while ! self.tx_ready() {}
                            unsafe {
                                self.spi_fifo_ptr.write_volatile(full_word as u32)
                            }
                        } else {
                            self.registers.phy().write(|w| unsafe { w.length().bits(8) });
                            for byte in chunk {
                                while ! self.tx_ready() {}
                                unsafe {
                                    self.spi_fifo_ptr.write_volatile(*byte as u32)
                                }
                            }
                        }
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

                // Wait for the SPI peripheral to indicate that there is no ongoing transaction
                fn flush(&mut self) -> Result<(), SpiError> {
                    while self.registers.status().read().bus_busy().bit() {}
                    Ok(())
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
                    self.flush()?;
                    Ok(())
                }
            }
        )+
    };
}
