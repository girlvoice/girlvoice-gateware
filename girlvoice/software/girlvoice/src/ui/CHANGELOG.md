the UI now uses the embedded-graphics framebuffer:
  - data_mut() for direct access to raw bytes for fading effect
  - set_pixel() for writing individual pixels
  - pixel() for reading individual pixels (for transparent UI elements)

other changes:
  - removed static mut FRAMEBUFFER. now using embedded_graphics::framebuffer::Framebuffer
  - framebuffer uses BigEndian byte order to match the GC9A01 display
  - fade_framebuffer() operates on &mut [u8] form fb.data_mut()
  - display uses basic mode (not buffered_graphics) and we write the framebuffer via draw_buffer()
  - removed trail_history from visualizer since framebuffer fading handles trails
