#[macro_export]
macro_rules! spi {
    ($(
        $SPIX:ident: ($PACSPIX:ty, $WORD:ty),
    )+) => {
        $(

            #[derive(Debug)]
            pub struct $SPIX {
                registers: $PACSPIX
            }

            #[derive(Debug, Copy, Clone, Eq, PartialEq)]
            pub enum Error {
                TransactionFailed,
                InvalidState,
                Failed,
            }
            impl $crate::hal::spi::Error for Error {
                fn kind(&self) -> hal::spi::ErrorKind {
                    match *self {
                        Error::TransactionFailed => $crate::hal::spi::ErrorKind::Other,
                        Error::InvalidState => $crate::hal::spi::ErrorKind::Other,
                        Error::Failed => $crate::hal::spi::ErrorKind::Other,
                    }
                }
            }

            impl hal::spi::ErrorType for $SPIX {
                type Error = Error;
            }

            impl $SPIX {
                pub fn new(registers: $PACSPIX) -> Self {
                    Self { registers }
                }

                pub fn free(self) -> $PACSPIX {
                    self.registers
                }

                fn write_one(&mut self, word: &u8) -> Result<(), Error> {
                    if self.registers.status().read().done().bit() {
                        unsafe {
                            self.registers.mosi().write(|w| w.bits(word.into()));
                            self.registers.control().write(|w| {
                                w.length().bits(8).start().bit(true)
                            });
                        }
                        Ok(())
                    } else {
                        Err(Error::InvalidState)
                    }
                }

                fn is_done(&mut self) -> bool {
                    self.registers.status().read().done().bit()
                }

                fn read_priv(&mut self, bufs: &mut [$WORD]) ->  Result<(), Error> {
                    if self.registers.status().read().done().bit() {
                        for buf in bufs.iter_mut() {
                            unsafe {
                                self.registers.control().write(|w| {
                                    w.length().bits(8).start().bit(true)
                                });
                            }
                            while !self.is_done() {}
                            *buf = self.registers.miso().read().bits() as u8;
                        }
                        Ok(())
                    } else {
                        Err(Error::InvalidState)
                    }
                }

                fn write_priv(&mut self, words: &[u8]) -> Result<(), Error> {
                    if self.registers.status().read().done().bit() {
                        for word in words.iter() {
                            self.write_one(word);
                            while !self.is_done() {}
                        }
                        Ok(())
                    } else {
                        Err(Error::InvalidState)
                    }
                }

                fn transfer_priv(&mut self, read: &mut [$WORD], write: &[$WORD]) -> Result<(), Error> {
                    let len = read.len().max(write.len());
                    for i in 0..len {
                        let wb = write.get(i).copied().unwrap_or(0);

                        self.write_one(&wb);
                        while !self.is_done() {}
                        let rb = self.registers.miso().read().bits() as u8;
                        if let Some(r) = read.get_mut(i) {
                            *r = rb;
                        }
                    }
                    Ok(())
                }

                fn transfer_in_place_priv(&mut self, words: &mut [u8]) -> Result<(), Error> {
                    if self.is_done() {
                        for word in words.iter_mut() {
                            self.write_one(word);
                            while !self.is_done() {}
                            *word = self.registers.miso().read().bits() as u8;
                        }
                        Ok(())
                    } else {
                        Err(Error::InvalidState)
                    }
                }
            }


            impl hal::spi::SpiDevice<u8> for $SPIX {

                fn transaction(&mut self, operations: &mut [hal::spi::Operation<'_, u8>]) -> Result<(), Self::Error> {

                    for op in operations {
                        match op {
                            hal::spi::Operation::Read(buf) => self.read_priv(buf)?,
                            hal::spi::Operation::Write(buf) => self.write_priv(buf)?,
                            hal::spi::Operation::Transfer(read_buf, write_buf) => self.transfer_priv(read_buf, write_buf)?,
                            hal::spi::Operation::TransferInPlace(buf) => self.transfer_in_place(buf)?,
                            hal::spi::Operation::DelayNs(_) => continue,
                        }
                    }

                    Ok(())
                }

            }
        )+

    };
}

// impl hal::spi::SpiBus<u8> for $SPIX {

//     fn flush(&mut self) -> Result<(), Self::Error>{
//         while !self.is_done() {}
//         Ok(())
//     }
// }