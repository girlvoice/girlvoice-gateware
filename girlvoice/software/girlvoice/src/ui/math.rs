// Fixed-point math helpers with LUT based sin/cos
// - I16F16 fixed-point format (16 integer bits, 16 fractional bits)
// - 64-element lookup table for sin/cos operations

use fixed::types::I16F16;

pub type Fixed = I16F16;

const LUT_SIZE: usize = 64;

// some useful constants
pub mod consts {
    use super::Fixed;

    pub const ZERO: Fixed = Fixed::ZERO;
    pub const ONE: Fixed = Fixed::ONE;
    pub const HALF: Fixed = Fixed::lit("0.5");

    pub const FX_PI: Fixed = Fixed::lit("3.14159265358979");
    pub const FX_TAU: Fixed = Fixed::lit("6.28318530717958");
    pub const FX_FRAC_PI_2: Fixed = Fixed::lit("1.5707963267949");

    pub const DISPLAY_CENTER: Fixed = Fixed::const_from_int(crate::ui::DISPLAY_SIZE as i32 / 2);
    pub const DISPLAY_RADIUS: Fixed = Fixed::const_from_int(crate::ui::DISPLAY_CENTER as i32 - 10);

    pub const GOLDEN_RATIO: Fixed = Fixed::lit("1.618");
}

// calculate LUT for sine values for angles 0 to PI/2 (one quarter wave) at compile time
const SIN_LUT: [i32; LUT_SIZE] = {
    // each entry is sin(i * PI/2 / 63) for i in 0..64
    let mut lut = [0i32; LUT_SIZE];
    let mut i = 0;
    while i < LUT_SIZE {
        // angle = i * (PI/2) / (LUT_SIZE - 1)
        let angle = (i as f64) * core::f64::consts::FRAC_PI_2 / ((LUT_SIZE - 1) as f64);
        let sin_val = const_sin(angle);
        // convert to I16F16
        lut[i] = (sin_val * 65536.0 + 0.5) as i32;
        i += 1;
    }
    lut
};

// sin calculation using Taylor series
const fn const_sin(x: f64) -> f64 {
    // Taylor series: sin(x) = x - x^3/6 + x^5/120 - x^7/5040 + ...
    let x2 = x * x;
    let x3 = x2 * x;
    let x5 = x3 * x2;
    let x7 = x5 * x2;
    let x9 = x7 * x2;
    let x11 = x9 * x2;
    x - x3 / 6.0 + x5 / 120.0 - x7 / 5040.0 + x9 / 362880.0 - x11 / 39916800.0
}

// fixed-point sine using 64-element LUT with linear interpolation
pub fn fx_sin(angle: Fixed) -> Fixed {
    // normalize angle to [0, TAU)
    let mut a = angle % consts::FX_TAU;
    if a < Fixed::ZERO {
        a = a + consts::FX_TAU;
    }

    let half_pi = consts::FX_FRAC_PI_2;
    let quadrant = (a / half_pi).to_num::<i32>() as u8;
    let local_angle = a % half_pi;

    // map local angle to LUT index
    // index_fp = local_angle / (PI/2) * (LUT_SIZE - 1)
    let scale = Fixed::from_num(LUT_SIZE - 1);
    let index_fp = (local_angle * scale) / half_pi;
    let index = index_fp.to_num::<usize>().min(LUT_SIZE - 2);
    let frac = index_fp - Fixed::from_num(index);

    let sin0 = Fixed::from_bits(SIN_LUT[index]);
    let sin1 = Fixed::from_bits(SIN_LUT[index + 1]);
    let interpolated = sin0 + (sin1 - sin0) * frac;

    // apply quadrant symmetry
    match quadrant & 3 {
        0 => interpolated,
        1 => {
            // sin(PI/2 + x) = sin(PI/2 - x) = cos(x)
            let mirror_idx_fp = scale - index_fp;
            let mirror_idx = mirror_idx_fp.to_num::<usize>().min(LUT_SIZE - 2);
            let mirror_frac = mirror_idx_fp - Fixed::from_num(mirror_idx);
            let s0 = Fixed::from_bits(SIN_LUT[mirror_idx]);
            let s1 = Fixed::from_bits(SIN_LUT[(mirror_idx + 1).min(LUT_SIZE - 1)]);
            s0 + (s1 - s0) * mirror_frac
        }
        2 => -interpolated,
        _ => {
            let mirror_idx_fp = scale - index_fp;
            let mirror_idx = mirror_idx_fp.to_num::<usize>().min(LUT_SIZE - 2);
            let mirror_frac = mirror_idx_fp - Fixed::from_num(mirror_idx);
            let s0 = Fixed::from_bits(SIN_LUT[mirror_idx]);
            let s1 = Fixed::from_bits(SIN_LUT[(mirror_idx + 1).min(LUT_SIZE - 1)]);
            -(s0 + (s1 - s0) * mirror_frac)
        }
    }
}

// fixed-point cosine using sin(angle + PI/2)
pub fn fx_cos(angle: Fixed) -> Fixed {
    fx_sin(angle + consts::FX_FRAC_PI_2)
}

// fixed-point square root approximation using Newton-Raphson
pub fn fx_sqrt(x: Fixed) -> Fixed {
    if x <= Fixed::ZERO {
        return Fixed::ZERO;
    }

    let mut guess = x >> 1;
    if guess == Fixed::ZERO {
        guess = Fixed::from_num(1);
    }

    // Newton-Raphson iterations: guess = (guess + x/guess) / 2
    for _ in 0..8 {
        let new_guess = (guess + x / guess) >> 1;
        if new_guess == guess {
            break;
        }
        guess = new_guess;
    }
    guess
}

// fixed-point absolute value
pub fn fx_abs(x: Fixed) -> Fixed {
    if x < Fixed::ZERO {
        -x
    } else {
        x
    }
}

// convert f32 to Fixed
pub fn fx_from_f32(x: f32) -> Fixed {
    Fixed::from_num(x)
}

// convert Fixed to f32
pub fn fx_to_f32(x: Fixed) -> f32 {
    x.to_num::<f32>()
}

// convert Fixed to i32
pub fn fx_to_i32(x: Fixed) -> i32 {
    x.to_num::<i32>()
}

// 2D point rotation using fixed-point coordinates
#[derive(Clone, Copy, Default)]
pub struct FxPoint2D {
    pub x: Fixed,
    pub y: Fixed,
}

impl FxPoint2D {
    pub const fn new(x: Fixed, y: Fixed) -> Self {
        Self { x, y }
    }

    pub fn from_f32(x: f32, y: f32) -> Self {
        Self {
            x: Fixed::from_num(x),
            y: Fixed::from_num(y),
        }
    }

    pub fn rotate(self, angle: Fixed) -> Self {
        let sin_a = fx_sin(angle);
        let cos_a = fx_cos(angle);
        Self {
            x: self.x * cos_a - self.y * sin_a,
            y: self.x * sin_a + self.y * cos_a,
        }
    }

    pub fn scale(self, factor: Fixed) -> Self {
        Self {
            x: self.x * factor,
            y: self.y * factor,
        }
    }

    pub fn to_screen(self) -> (i32, i32) {
        (
            fx_to_i32(consts::DISPLAY_CENTER + self.x * consts::DISPLAY_RADIUS),
            fx_to_i32(consts::DISPLAY_CENTER + self.y * consts::DISPLAY_RADIUS),
        )
    }
}
