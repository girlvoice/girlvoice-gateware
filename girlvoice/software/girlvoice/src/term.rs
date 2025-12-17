
use embedded_io::{Read, Write};
use fixedstr::*;
pub struct Terminal<T: Read + Write> {
    serial: T,
    cmd_str: zstr<256>,
    prev_cmd: zstr<256>,
    char_buf: [u8; 1],
    csi_mode: bool
}

fn parse_addr(addr_token: &str) -> Option<u32> {
    if let Some(unprefixed) = addr_token.strip_prefix("0x") {
        u32::from_str_radix(unprefixed, 16).ok()
    } else {
        None
    }
}

impl<T: Read + Write> Terminal<T> {
    pub fn new(serial: T) -> Self {
        Self {
            serial: serial,
            cmd_str: zstr::default(),
            prev_cmd: zstr::default(),
            char_buf: [0],
            csi_mode: false
        }
    }

    pub fn handle_char(&mut self) {

        let read_size = self.serial.read(&mut self.char_buf).unwrap();
        let new_char = self.char_buf[0] as char;
        if self.csi_mode {
            self.handle_csi_command(new_char);
        } else {
            match new_char {
                '\r' => {
                    self.serial.write(b"\r\n").unwrap();
                    self.prev_cmd = self.cmd_str;
                    self.handle_cmd();
                    self.cmd_str.clear();
                    write!(self.serial, "[girlvoice (^O^)~] ").unwrap();
                },

                '\u{7F}' | '\u{08}' => { // delete
                    if self.cmd_str.len() != 0 {
                        self.cmd_str.pop_char();
                        self.serial.write(&['\u{08}' as u8]).unwrap();
                        self.serial.write(&[0x1b, b'[', b'K']).unwrap();
                    }

                },
                '\u{20}' ..= '\u{7E}' => { // regular chars
                    self.serial.write(&[new_char as u8]).unwrap();
                    self.cmd_str.push_char(new_char);
                },
                '\u{1B}' => {
                    let _ = self.serial.read(&mut self.char_buf).unwrap();
                    match self.char_buf[0] as char {
                        '[' => self.csi_mode = true,
                        _ => {}
                    };
                }
                _ => { // Unknown character
                    // self.serial.write(&[new_char as u8]).unwrap();
                }

            }
        };
    }

    fn handle_csi_command(&mut self, new_char: char) {
        match new_char {
            '\u{0041}' => {
                if !self.cmd_str.is_empty() {
                    let cmd_len = (self.cmd_str.len()) as u8;
                    for _ in 0..cmd_len {
                        self.serial.write(&[0x1b, b'[', b'D']).unwrap(); // move back to the start of the command
                    }
                    self.serial.write(&[0x1b, b'[', b'K']).unwrap(); // Clear everything past the cursor
                }
                write!(self.serial, "{}", self.prev_cmd).unwrap(); // print the new command
                self.cmd_str = self.prev_cmd;
            },
            _ => {
                writeln!(self.serial, "got command char: {:#x}\r", new_char as u8).unwrap();
            }
        };
        self.csi_mode = false;

    }

    fn handle_cmd(&mut self) {
        if self.cmd_str.len() == 0 {
            return;
        }

        let mut split = self.cmd_str.split_whitespace();

        let cmd = split.next();
        match cmd {
            Some("read") => {
                if let Some(addr_token) = split.next() {
                    if let Some(addr) = parse_addr(addr_token) {
                        let addr_ptr = addr as *mut u8;

                        let data: u8 = unsafe { core::ptr::read(addr_ptr) };
                        writeln!(self.serial, "{:#x}: {:#x}\r",addr, data).unwrap();
                        return;
                    }
                }
                writeln!(self.serial, "usage: read 0x<addr>\r").unwrap();

            },
            Some("write") => {
                if let Some(addr_token) = split.next() {
                    if let Some(addr) = parse_addr(addr_token) {
                        let addr_ptr = addr as *mut u8;
                        if let Some(data_token) =  split.next() {
                            match data_token.strip_prefix("0x") {
                                Some(stripped_data) => {
                                    if let Ok(new_data) = u8::from_str_radix(stripped_data, 16) {
                                        unsafe { *addr_ptr = new_data};
                                        writeln!(self.serial, "{:#x}\r", new_data).unwrap();
                                    }
                                },
                                None => {
                                    if let Ok(new_data) = data_token.parse::<u8>() {
                                        unsafe { *addr_ptr = new_data};
                                        writeln!(self.serial, "{:#x}\r", new_data).unwrap();
                                    }
                                }
                            }
                            return;
                        }
                    }
                }
                writeln!(self.serial, "usage: write 0x<addr> <data>\r").unwrap();
            },
            Some(_) => writeln!(self.serial, "idk how to do that yet\r").unwrap(),
            None => writeln!(self.serial, "ouch that hurt!").unwrap(),
            _ => writeln!(self.serial, "ouchieee").unwrap(),
        };
    }

}