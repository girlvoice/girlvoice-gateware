
use core::fmt::write;

use embedded_io::{Read, Write};
use embedded_hal::i2c::I2c;
use embedded_hal::delay::DelayNs;
use fixedstr::*;
use aw88395::Aw88395;

pub struct Terminal<T: Read + Write, U: I2c, V: DelayNs> {
    serial: T,
    cmd_str: zstr<256>,
    prev_cmd: zstr<256>,
    char_buf: [u8; 1],
    csi_mode: bool,
    amp: Aw88395<U>,
    timer: V
}

fn parse_addr(addr_token: &str) -> Option<u32> {
    if let Some(unprefixed) = addr_token.strip_prefix("0x") {
        u32::from_str_radix(unprefixed, 16).ok()
    } else {
        None
    }
}

impl<T: Read + Write, U: I2c, V: DelayNs> Terminal<T, U, V> {
    pub fn new(serial: T, amp: Aw88395<U>, timer: V) -> Self {
        Self {
            serial: serial,
            cmd_str: zstr::default(),
            prev_cmd: zstr::default(),
            char_buf: [0],
            csi_mode: false,
            amp: amp,
            timer: timer
        }
    }

    pub fn delay_ms(&mut self, ms: u32) {
        self.timer.delay_ms(ms);
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
            Some("init") => {
                self.initialize_amplifier();
            }
            Some("set_vol") => {
                if let Some(vol_token) = split.next() {
                    if let Ok(vol_percent) = vol_token.parse::<u16>() {
                        match self.amp.set_volume_percent(vol_percent) {
                            Ok(volume_reg) => writeln!(self.serial, "Set volume register to {}\r", volume_reg).unwrap(),
                            Err(_) => writeln!(self.serial, "Failed to set volume\r").unwrap(),
                        }
                    }
                } else {
                    writeln!(self.serial, "usage: set_vol <volume> : Set the amplifier volume on a scale from 0-100%\r").unwrap();
                }
            }
            Some(_) => writeln!(self.serial, "idk how to do that yet\r").unwrap(),
            None => writeln!(self.serial, "ouch that hurt!\r").unwrap(),
        };
    }

    fn initialize_amplifier(&mut self) {
        writeln!(self.serial, "Beginning amplifier initialization.\r").unwrap();
        if self.amp.soft_reset().is_err() {
            writeln!(self.serial, "Failed to reset amplifier\r").unwrap();
            let stat = self.amp.get_status_bits().unwrap();

            writeln!(self.serial, "Status register {:#x}", stat).unwrap();
            return;
        }
        if self.amp.power_on().is_err() {
            writeln!(self.serial, "Failed to power on amplifier\r").unwrap();
            return;
        }
        writeln!(self.serial, "Waiting for amp PLL lock\r").unwrap();
        if !self.wait_for_pll_lock() {
            writeln!(self.serial, "Failed to find PLL lock!\r").unwrap();
            let stat = self.amp.get_status_bits().unwrap();

            writeln!(self.serial, "Status register {:#x}", stat).unwrap();
            return;
        }

        if self.amp.set_volume(100).is_err() {
            writeln!(self.serial, "Failed to set initial amplifier volume\r").unwrap();
            return;
        }

        writeln!(self.serial, "Waiting for amp PLL lock\r").unwrap();
        if self.amp.enable_i2s().is_err() {
            writeln!(self.serial, "Failed to enable i2s during amplifier init\r").unwrap();
            let stat = self.amp.get_status_bits().unwrap();

            writeln!(self.serial, "Status register {:#x}", stat).unwrap();
            return;
        }
        writeln!(self.serial, "Enabling class D amplifier and boost converter\r").unwrap();
        if self.amp.enable_amp().is_err() {
            writeln!(self.serial, "Failed to enable boost amplifier\r").unwrap();
            return;
        }
        if !self.wait_for_amp_pwr() {
            writeln!(self.serial, "Failed to power on boost amplifier\r").unwrap();
            let stat = self.amp.get_status_bits().unwrap();

            writeln!(self.serial, "Status register {:#x}", stat).unwrap();
            return;
        }

        writeln!(self.serial, "Unmuting...\r").unwrap();
        if self.amp.unmute().is_err() {
            writeln!(self.serial, "Failed to unmute amplifier\r").unwrap();
            let stat = self.amp.get_status_bits().unwrap();

            writeln!(self.serial, "Status register {:#x}\r", stat).unwrap();
            return;
        }

    }

    fn wait_for_pll_lock(&mut self) -> bool {
        const MAX_RETRIES: i32 = 2;
        for _ in 0..MAX_RETRIES {
            match self.amp.pll_locked() {
                Ok(is_enabled) => {
                    if is_enabled {
                        writeln!(self.serial, "done!\r").unwrap();
                        return true;
                    } else {
                        self.timer.delay_ms(500);
                        write!(self.serial, ".").unwrap();
                    }
                }
                Err(_) => {
                    writeln!(self.serial, "Failed to query PLL status\r").unwrap();
                    return false;
                }
            }
        }
        false
    }

    fn wait_for_amp_pwr(&mut self) -> bool {
        const MAX_RETRIES: i32 = 3;
        for _ in 0..MAX_RETRIES {
            match self.amp.boost_init_finished() {
                Ok(is_enabled) => {
                    if is_enabled {
                        writeln!(self.serial, "done!\r").unwrap();
                        return true;
                    } else {
                        write!(self.serial, ".").unwrap();
                        self.timer.delay_ms(1000);
                    }
                }
                Err(_) => {
                    writeln!(self.serial, "Failed to query boost converter status\r").unwrap();
                    return false;
                }
            }
        }
        false
    }

}