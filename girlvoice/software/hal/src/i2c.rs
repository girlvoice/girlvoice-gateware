use core::u8;

use soc_pac::I2cfifo;
use embedded_hal::i2c::SevenBitAddress;
use embedded_hal::i2c::{self, I2c, Operation};

#[allow(dead_code)]

#[derive(Debug, Copy, Clone, Eq, PartialEq)]
pub enum Error {
    TransactionFailed,
    InvalidState,
    RxUnderflow,
    ReceivedNack,
}

pub enum TxCmd {
    DataByte = 0x0,
    LastByte = 0x1,
    StartCount = 0x2,
    RestartCount = 0x3,
}

pub struct I2c0 {
    registers: I2cfifo,
}

impl I2c0 {
    pub fn new(registers: I2cfifo) -> Self {
        Self { registers}
    }

    fn is_read_complete(&mut self) -> bool {
        self.registers.i2cfifosr_msb().read().rdcmpl().bit()
    }

    fn is_bus_busy(&mut self) -> bool {
        self.registers.i2cfifosr_lsb().read().busy().bit()
    }

    pub fn received_nack(&mut self) -> bool {
        self.registers.i2cfifosr_lsb().read().rnack().bit()
    }

    fn check_rx_underflow(&mut self) -> bool {
        self.registers.i2cfifosr_msb().read().rxunderfl().bit()
    }

    // TX FIFO can be reset to known-good state by reading from it.
    fn reset_tx_fifo(&mut self) {
        self.registers.i2ctxfifo_lsb().read().bits();
    }

    // RX FIFO can be reset to known-good state by writing anything to it.
    fn reset_rx_fifo(&mut self) {
        self.registers.i2crxfifo().write(|w| unsafe{ w.bits(0) });
    }

    fn push_tx_byte(&mut self, byte: u8, cmd: TxCmd){
        self.registers.i2ctxfifo_lsb().write(|w| unsafe{ w.txlsb().bits(byte) });
        self.registers.i2ctxfifo_msb().write(|w| unsafe{ w.cmd().bits(cmd as u8)} );
    }

    fn pop_rx_byte(&mut self) -> u8 {
        let byte = self.registers.i2crxfifo().read().rx_data().bits();
        byte
    }

    // fn read_internal( &mut self, address: SevenBitAddress, buffer: &mut [u8]) -> Result<(), Error> {
    //     let buf_len = buffer.len() as u8;
    //     if buf_len > 31 {
    //         return Err(Error::RxUnderflow);
    //     }

    //     self.push_tx_byte(buf_len, TxCmd::RestartCount);
    //     self.push_tx_byte((address << 1) | 1, TxCmd::DataByte);

    //     while !self.is_read_complete() {
    //         // if self.recieved_nack() {
    //         //     return Err(Error::TransactionFailed);
    //         // }
    //     }

    //     for byte in buffer.iter_mut() {
    //         *byte = self.pop_rx_byte();
    //         // if self.check_rx_underflow() {
    //         //     return Err(Error::RxUnderflow);
    //         // }
    //     }
    //     self.reset_rx_fifo();
    //     Ok(())
    // }

    fn write_internal( &mut self, address: SevenBitAddress, bytes: &[u8]) -> Result<(), Error> {
        let len = bytes.len();
        let bytes = bytes.into_iter();
        self.reset_tx_fifo();

        if self.is_bus_busy() {return Err(Error::InvalidState);}

        self.push_tx_byte(0, TxCmd::RestartCount);
        self.push_tx_byte(address << 1, TxCmd::DataByte);

        for (i, byte) in bytes.enumerate() {
            let last = i == len - 1;
            self.push_tx_byte(*byte, if last { TxCmd::LastByte } else { TxCmd::DataByte });
        }

        if self.received_nack() { return Err(Error::TransactionFailed) }

        while self.is_bus_busy() {}

        Ok(())
    }
}

impl i2c::Error for Error {
    fn kind(&self) -> i2c::ErrorKind {
        match *self {
            Error::RxUnderflow => i2c::ErrorKind::Other,
            Error::TransactionFailed => i2c::ErrorKind::Bus,
            Error::InvalidState => i2c::ErrorKind::Other,
            Error::ReceivedNack => i2c::ErrorKind::NoAcknowledge(i2c::NoAcknowledgeSource::Unknown),
        }
    }
}

impl i2c::ErrorType for I2c0 {
    type Error = Error;
}

impl I2c<SevenBitAddress> for I2c0 {
    fn transaction(&mut self, address: SevenBitAddress, operations: &mut [Operation]) -> Result<(), Self::Error> {

        for op in operations {
            match op {
                Operation::Read(buf) => continue,
                Operation::Write(buf) => self.write_internal(address, buf)?,
            }
        }

        Ok(())
    }

    fn write_read(&mut self, address: SevenBitAddress, write: &[u8], read: &mut [u8]) -> Result<(), Self::Error> {
        let buf_len = read.len() as u8;
        // if buf_len > 31 {
        //     return Err(Error::RxUnderflow);
        // }

        self.reset_tx_fifo();

        if self.is_bus_busy() {return Err(Error::InvalidState);}

        self.push_tx_byte(0, TxCmd::RestartCount);
        self.push_tx_byte(address << 1, TxCmd::DataByte);

        for byte in write.into_iter() {
            self.push_tx_byte(*byte, TxCmd::DataByte);
        }

        // For some reason the I2CFIFO seems to always read one more than the number of bytes you tell it to read.
        self.push_tx_byte(buf_len + 1, TxCmd::RestartCount);
        self.push_tx_byte((address << 1) | 1, TxCmd::DataByte);

        // if !self.is_bus_busy() {
        //     return Err(Error::TransactionFailed);
        // }

        while !self.is_read_complete() {
            if self.received_nack() {
                self.reset_rx_fifo();
                return Err(Error::ReceivedNack);
            }
        }

        for byte in read.iter_mut() {
            *byte = self.pop_rx_byte();
            if self.check_rx_underflow() {
                self.reset_rx_fifo();
                return Err(Error::RxUnderflow);
            }
        }
        // Block until transaction is finished
        while self.is_bus_busy() {
        }

        self.reset_rx_fifo();

        Ok(())
    }
}