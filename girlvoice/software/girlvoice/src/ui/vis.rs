use crate::ui::{
    math::{self, Fixed, FxPoint2D},
    Color, ColorPalette, EnvelopeSmoother, LFO, Point2D,
    DISPLAY_SIZE, draw_line, draw_thick_line,
};

const MAX_CHANNELS: usize = crate::ui::MAX_CHANNELS;

// available visualizers
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ModeKind {
    HarmonicLoop,
    BarMeter,
}

impl ModeKind {
    pub fn name(&self) -> &'static str {
        match self {
            ModeKind::HarmonicLoop => "Harmonic Loop",
            ModeKind::BarMeter => "Bar Meter",
        }
    }
}

// simple bar meter for debugging
pub struct BarMeter {
    num_channels: usize,
    energies: [f32; MAX_CHANNELS],
}

impl BarMeter {
    pub fn new(num_channels: usize) -> Self {
        Self {
            num_channels,
            energies: [0.0; MAX_CHANNELS],
        }
    }

    pub fn update(&mut self, _dt: f32, energies: &[f32]) {
        for i in 0..self.num_channels.min(MAX_CHANNELS) {
            self.energies[i] = energies.get(i).copied().unwrap_or(0.0);
        }
    }

    pub fn render<F>(&self, mut set_pixel: F, pal: &ColorPalette)
    where
        F: FnMut(usize, usize, Color),
    {
        let num_bars = self.num_channels.min(14);
        let bar_width = (DISPLAY_SIZE - 20) / num_bars; // fit all bars with margin
        let gap = 2;
        let max_height = DISPLAY_SIZE - 60; // leave margin top and bottom
        let min_height = 10; // minimum bar height

        for i in 0..num_bars {
            let energy = self.energies[i].clamp(0.0, 1.0);
            let bar_height = min_height + (energy * (max_height - min_height) as f32) as usize;

            let x_start = 10 + i * bar_width;
            let x_end = x_start + bar_width - gap;
            let y_bottom = DISPLAY_SIZE - 80;
            let y_top = y_bottom.saturating_sub(bar_height);

            // get color from palette based on channel index
            let color = pal.sample(i as f32 / num_bars as f32);

            // draw filled bar
            for x in x_start..x_end.min(DISPLAY_SIZE) {
                for y in y_top..y_bottom.min(DISPLAY_SIZE) {
                    let brightness = 0.4 + 0.6 * (1.0 - (y - y_top) as f32 / bar_height.max(1) as f32);
                    set_pixel(x, y, color.scale(brightness));
                }
            }
        }
    }
}

// harmonic Loop. A single closed figure where each channel adds harmonic deformation
// - Base shape of a circle, x = cos(t), y = sin(t)
// - Each channel adds x += A_n * cos(n*t + phi), y += A_n * sin(n*t + phi')
pub struct HarmonicLoop {
    num_channels: usize,
    smoothers: [EnvelopeSmoother; MAX_CHANNELS],
    energies: [f32; MAX_CHANNELS],
    rotation: LFO,
    harmonic_phases: [LFO; MAX_CHANNELS],
    total_energy: EnvelopeSmoother,
    resolution: usize,
}

impl HarmonicLoop {
    pub fn new(num_channels: usize) -> Self {
        Self {
            num_channels,
            smoothers: core::array::from_fn(|_| EnvelopeSmoother::new(60.0, 5.0, 80.0)),
            energies: [0.0; MAX_CHANNELS],
            rotation: LFO::new(0.02),
            harmonic_phases: core::array::from_fn(|i| {
                LFO::new_with_phase(0.08 + (i as f32 * 0.03), i as f32 * 0.4)
            }),
            total_energy: EnvelopeSmoother::new(60.0, 2.0, 50.0),
            resolution: 80, // reduced from 200 for better performance
        }
    }

    fn sample_point(&self, t: f32, rotation: f32) -> Point2D {
        // use fixed-point LUT for all sin/cos operations
        let t_fx = math::fx_from_f32(t);
        let mut x = math::fx_cos(t_fx);
        let mut y = math::fx_sin(t_fx);

        // add harmonics from each channel
        for i in 0..self.num_channels {
            let energy = self.energies[i];
            if energy < 0.01 {
                continue;
            }

            // harmonic number: lower channels = lower harmonics (rounder), higher = more detail
            let harmonic = Fixed::from_num(i + 2);
            let phase = math::fx_from_f32(self.harmonic_phases[i].phase);

            // falloff for higher harmonics
            let amp = math::fx_from_f32(energy * 0.35 / (1.0 + i as f32 * 0.08));

            // phase difference between X and Y creates the lissajous-like asymmetry
            let angle_x = harmonic * t_fx + phase;
            let angle_y = harmonic * t_fx + phase * math::consts::GOLDEN_RATIO;
            x = x + amp * math::fx_cos(angle_x);
            y = y + amp * math::fx_sin(angle_y);
        }

        // scale based on total energy
        let scale = math::fx_from_f32(0.45 + 0.35 * self.total_energy.value());
        let fx_point = FxPoint2D::new(x * scale, y * scale).rotate(math::fx_from_f32(rotation));
        Point2D::new(math::fx_to_f32(fx_point.x), math::fx_to_f32(fx_point.y))
    }

    pub fn update(&mut self, dt: f32, energies: &[f32]) {
        self.rotation.tick(dt);

        for lfo in &mut self.harmonic_phases[..self.num_channels] {
            lfo.tick(dt);
        }

        let mut total = 0.0f32;
        for i in 0..self.num_channels {
            let e = energies.get(i).copied().unwrap_or(0.0);
            self.energies[i] = self.smoothers[i].process(e);
            total += self.energies[i];
        }
        self.total_energy.process(total / self.num_channels as f32);
    }

    pub fn render<F>(&self, set_pixel: F, pal: &ColorPalette)
    where
        F: FnMut(usize, usize, Color),
    {
        self.render_with_palette(set_pixel, pal);
    }

    pub fn render_with_palette<F>(&self, mut set_pixel: F, pal: &ColorPalette)
    where
        F: FnMut(usize, usize, Color),
    {
        // draw main figure using palette colors
        let rotation = self.rotation.phase;
        for i in 0..self.resolution {
            let t0 = (i as f32 / self.resolution as f32) * core::f32::consts::TAU;
            let t1 = ((i + 1) as f32 / self.resolution as f32) * core::f32::consts::TAU;

            let p0 = self.sample_point(t0, rotation);
            let p1 = self.sample_point(t1, rotation);
            let (sx0, sy0) = p0.to_screen();
            let (sx1, sy1) = p1.to_screen();

            // use palette gradient around the figure
            let color = pal.sample(i as f32 / self.resolution as f32);
            let brightness = 1.0; // 0.7 + 0.3 * self.total_energy.value();

            draw_line(sx0, sy0, sx1, sy1, color.scale(brightness), &mut set_pixel);
        }

        // draw bright spots at high-energy harmonics (simplified for performance)
        /*for i in 0..self.num_channels {
            if self.energies[i] > 0.5 {
                let harmonic = (i + 2) as f32;
                let t = self.harmonic_phases[i].phase / harmonic;
                let point = self.sample_point(t, rotation);
                let (sx, sy) = point.to_screen();
                let color = pal.sample(i as f32 / self.num_channels as f32);
                let energy = self.energies[i];

                // simplified 3x3 bright spot (no sqrt, uses lookup table for brightness)
                const BRIGHTNESS: [[f32; 3]; 3] = [
                    [0.3, 0.6, 0.3],
                    [0.6, 1.0, 0.6],
                    [0.3, 0.6, 0.3],
                ];
                for dy in 0..3i32 {
                    for dx in 0..3i32 {
                        let (px, py) = (sx + dx - 1, sy + dy - 1);
                        if px >= 0 && px < DISPLAY_SIZE as i32 && py >= 0 && py < DISPLAY_SIZE as i32 {
                            let (ux, uy) = (px as usize, py as usize);
                            if !self.circular_mask || is_in_circle(ux, uy) {
                                let b = BRIGHTNESS[dy as usize][dx as usize] * energy;
                                set_pixel(ux, uy, color.scale(b));
                            }
                        }
                    }
                }
            }
        }*/
    }
}


// main visualizer mode switching
pub struct Visualizer {
    harmonic_loop: HarmonicLoop,
    bar_meter: BarMeter,
    current_mode: ModeKind,
    palette: ColorPalette
}

impl Visualizer {
    pub fn new(num_channels: usize) -> Self {
        Self {
            harmonic_loop: HarmonicLoop::new(num_channels),
            bar_meter: BarMeter::new(num_channels),
            current_mode: ModeKind::HarmonicLoop,
            palette: ColorPalette::default(),
        }
    }

    pub fn update(&mut self, dt: f32, energies: &[f32]) {
        match self.current_mode {
            ModeKind::HarmonicLoop => self.harmonic_loop.update(dt, energies),
            ModeKind::BarMeter => self.bar_meter.update(dt, energies),
        }
    }

    pub fn render<F>(&self, set_pixel: F)
    where
        F: FnMut(usize, usize, Color),
    {
        match self.current_mode {
            ModeKind::HarmonicLoop => self.harmonic_loop.render(set_pixel, &self.palette),
            ModeKind::BarMeter => self.bar_meter.render(set_pixel, &self.palette),
        }
    }

    pub fn current_mode(&self) -> ModeKind {
        self.current_mode
    }

    pub fn set_mode(&mut self, mode: ModeKind) {
        self.current_mode = mode;
    }

    pub fn set_palette(&mut self, palette: ColorPalette) {
        self.palette = palette;
    }

    pub fn palette(&self) -> &ColorPalette {
        &self.palette
    }
}
