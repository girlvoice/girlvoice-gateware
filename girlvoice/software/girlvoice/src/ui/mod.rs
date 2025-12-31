pub mod math;
mod vis;
pub use vis::{Visualizer, ModeKind};
pub use math::{Fixed, FxPoint2D};

use libm::fabsf;

// display config (round 240x240 1.8" LCD, GC9A01)
pub const DISPLAY_SIZE: usize = 240;
pub const DISPLAY_CENTER: f32 = (DISPLAY_SIZE / 2) as f32;
pub const DISPLAY_RADIUS: f32 = DISPLAY_CENTER - 10.0;

// DSP config
pub const MAX_CHANNELS: usize = 16;

#[derive(Clone, Copy)]
pub struct Color {
    pub r: u8,
    pub g: u8,
    pub b: u8,
}

impl Default for Color {
    fn default() -> Self {
        Self { r: 0, g: 0, b: 0 }
    }
}

impl Color {
    pub const fn new(r: u8, g: u8, b: u8) -> Self {
        Self { r, g, b }
    }

    // use RGB565 for embedded display
    pub fn to_rgb565(self) -> u16 {
        let r = (self.r as u16 >> 3) & 0x1F;
        let g = (self.g as u16 >> 2) & 0x3F;
        let b = (self.b as u16 >> 3) & 0x1F;
        (r << 11) | (g << 5) | b
    }

    // use to 24bit RGB for simulator
    pub fn to_argb32(self) -> u32 {
        0xFF000000 | ((self.r as u32) << 16) | ((self.g as u32) << 8) | (self.b as u32)
    }

    // interpolate between two colors
    pub fn lerp(a: Color, b: Color, t: f32) -> Color {
        let t = t.clamp(0.0, 1.0);
        Color {
            r: (a.r as f32 * (1.0 - t) + b.r as f32 * t) as u8,
            g: (a.g as f32 * (1.0 - t) + b.g as f32 * t) as u8,
            b: (a.b as f32 * (1.0 - t) + b.b as f32 * t) as u8,
        }
    }

    // color from HSV (hue 0-360, sat/val 0-1)
    pub fn from_hsv(h: f32, s: f32, v: f32) -> Color {
        let h = h % 360.0;
        let c = v * s;
        let x = c * (1.0 - fabsf((h / 60.0) % 2.0 - 1.0));
        let m = v - c;

        let (r, g, b) = if h < 60.0 {
            (c, x, 0.0)
        } else if h < 120.0 {
            (x, c, 0.0)
        } else if h < 180.0 {
            (0.0, c, x)
        } else if h < 240.0 {
            (0.0, x, c)
        } else if h < 300.0 {
            (x, 0.0, c)
        } else {
            (c, 0.0, x)
        };

        Color {
            r: ((r + m) * 255.0) as u8,
            g: ((g + m) * 255.0) as u8,
            b: ((b + m) * 255.0) as u8,
        }
    }

    pub fn scale(self, factor: f32) -> Color {
        Color {
            r: (self.r as f32 * factor) as u8,
            g: (self.g as f32 * factor) as u8,
            b: (self.b as f32 * factor) as u8,
        }
    }
}

pub struct ColorPalette {
    pub colors: [Color; 16],
    pub primary: Color,
    pub secondary: Color,
    pub accent: Color,
}


impl ColorPalette {
    pub fn new() -> Self {
        Self::default()
    }

    // get a color by index
    pub fn get(&self, index: usize) -> Color {
        self.colors[index % 16].clone()
    }

    // get a color by position
    pub fn sample(&self, t: f32) -> Color {
        let t = t.clamp(0.0, 0.9999);
        let idx = (t * 16.0) as usize;
        let frac = t * 16.0 - idx as f32;
        let next_idx = (idx + 1) % 16;
        Color::lerp(self.colors[idx].clone(), self.colors[next_idx].clone(), frac)
    }
}

impl Default for ColorPalette {
    fn default() -> Self {
        // default palette
        let colors = core::array::from_fn(|i| palette::rainbow(i as f32 / 16.0));
        Self {
            colors,
            primary: palette::PINK,
            secondary: palette::CYAN,
            accent: palette::PURPLE,
        }
    }
}

pub mod palette {
    use super::Color;

    pub const PINK: Color = Color::new(255, 20, 147);
    pub const CYAN: Color = Color::new(0, 255, 255);
    pub const PURPLE: Color = Color::new(148, 0, 211);
    pub const MAGENTA: Color = Color::new(255, 0, 255);
    pub const BLUE: Color = Color::new(30, 144, 255);
    pub const GREEN: Color = Color::new(0, 255, 127);
    pub const ORANGE: Color = Color::new(255, 140, 0);
    pub const YELLOW: Color = Color::new(255, 255, 0);
    pub const BLACK: Color = Color::new(0, 0, 0);
    pub const WHITE: Color = Color::new(255, 255, 255);

    // get a rainbow gradient based on position (0-1)
    pub fn rainbow(t: f32) -> Color {
        Color::from_hsv(t * 360.0, 1.0, 1.0)
    }
}


// exponential envelope follower for smoothing values
#[derive(Clone, Debug)]
pub struct EnvelopeSmoother {
    value: f32,
    attack: f32,
    release: f32,
}

impl EnvelopeSmoother {
    pub fn new(sample_rate: f32, attack_ms: f32, release_ms: f32) -> Self {
        let attack = libm::expf(-1.0 / (sample_rate * attack_ms / 1000.0));
        let release = libm::expf(-1.0 / (sample_rate * release_ms / 1000.0));
        Self { value: 0.0, attack, release }
    }

    pub fn process(&mut self, input: f32) -> f32 {
        let coeff = if input > self.value { self.attack } else { self.release };
        self.value = self.value * coeff + input * (1.0 - coeff);
        self.value
    }

    pub fn value(&self) -> f32 {
        self.value
    }
}

// basic oscillator
#[derive(Clone, Debug)]
pub struct LFO {
    pub phase: f32,
    pub frequency: f32,
}

impl LFO {
    pub fn new(frequency: f32) -> Self {
        Self { phase: 0.0, frequency }
    }

    pub fn new_with_phase(frequency: f32, initial_phase: f32) -> Self {
        Self { phase: initial_phase, frequency }
    }

    pub fn tick(&mut self, dt: f32) -> f32 {
        self.phase += self.frequency * dt * core::f32::consts::TAU;
        while self.phase > core::f32::consts::TAU {
            self.phase -= core::f32::consts::TAU;
        }
        math::fx_to_f32(math::fx_sin(math::fx_from_f32(self.phase)))
    }

    pub fn value(&self) -> f32 {
        math::fx_to_f32(math::fx_sin(math::fx_from_f32(self.phase)))
    }
}


// draw a line using Bresenham's algorithm
pub fn draw_line<F>(x0: i32, y0: i32, x1: i32, y1: i32, color: Color, circular_mask: bool, mut set_pixel: F)
where
    F: FnMut(usize, usize, Color),
{
    let dx = (x1 - x0).abs();
    let dy = -(y1 - y0).abs();
    let sx = if x0 < x1 { 1 } else { -1 };
    let sy = if y0 < y1 { 1 } else { -1 };
    let mut err = dx + dy;
    let (mut x, mut y) = (x0, y0);

    loop {
        if x >= 0 && x < DISPLAY_SIZE as i32 && y >= 0 && y < DISPLAY_SIZE as i32 {
            let (ux, uy) = (x as usize, y as usize);
            if !circular_mask || is_in_circle(ux, uy) {
                set_pixel(ux, uy, color);
            }
        }
        if x == x1 && y == y1 { break; }
        let e2 = 2 * err;
        if e2 >= dy { err += dy; x += sx; }
        if e2 <= dx { err += dx; y += sy; }
    }
}

// draw a thick line with glow effect
pub fn draw_thick_line<F>(x0: i32, y0: i32, x1: i32, y1: i32, thickness: i32, color: Color, circular_mask: bool, mut set_pixel: F)
where
    F: FnMut(usize, usize, Color),
{
    for offset in -thickness..=thickness {
        let (dx, dy) = (x1 - x0, y1 - y0);
        let len_sq = math::fx_from_f32((dx * dx + dy * dy) as f32);
        let len = math::fx_to_f32(math::fx_sqrt(len_sq)).max(1.0);
        let (nx, ny) = ((-dy as f32 / len * offset as f32) as i32, (dx as f32 / len * offset as f32) as i32);
        let fade = 1.0 - (offset.abs() as f32 / (thickness + 1) as f32);
        draw_line(x0 + nx, y0 + ny, x1 + nx, y1 + ny, color.scale(fade * fade), circular_mask, &mut set_pixel);
    }
}

// check if a screen point is within the display area (integer math)
pub fn is_in_circle(x: usize, y: usize) -> bool {
    let center = (DISPLAY_SIZE / 2) as i32;
    let dx = x as i32 - center;
    let dy = y as i32 - center;
    (dx * dx + dy * dy) <= (center * center)
}


// 2D point helper
#[derive(Clone, Copy, Default)]
pub struct Point2D {
    pub x: f32,
    pub y: f32,
}

impl Point2D {
    pub fn new(x: f32, y: f32) -> Self {
        Self { x, y }
    }

    pub fn to_screen(self) -> (i32, i32) {
        (
            (DISPLAY_CENTER + self.x * DISPLAY_RADIUS) as i32,
            (DISPLAY_CENTER + self.y * DISPLAY_RADIUS) as i32,
        )
    }
}
