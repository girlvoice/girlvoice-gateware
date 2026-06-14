#[derive(Debug)]
pub enum Error {
    Unspecified,
    InvalidParam,
    I2cNack,
}

impl From<sgtl5000::Sgtl5000Error> for Error {
    fn from(value: sgtl5000::Sgtl5000Error) -> Self {
        match value {
            sgtl5000::Sgtl5000Error::InvalidParam => Error::InvalidParam,
            sgtl5000::Sgtl5000Error::OpFailed => Error::I2cNack
        }
    }
}