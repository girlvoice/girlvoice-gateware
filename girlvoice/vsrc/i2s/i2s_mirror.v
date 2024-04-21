
module top (
	input  CLK,
  input P1A7,
  output P1A8,
  output P1A1,
  output P1A2,
  output P1A3,
  output P1A4,
  output LEDR_N
);

wire sclk;
wire mic_lr_clk;
wire amp_lr_clk;
wire amp_data;
wire mic_data;

// output wires
assign P1A1 = sclk;
assign P1A2 = mic_lr_clk;
//assign P1A3 = amp_lr_clk;
//assign P1A4 = amp_data;


// for testing

assign P1A3 = mic_lr_clk;
assign P1A4 = P1A7;
assign P1A8 = sclk;



// input wires
assign P1A7 = mic_data;


reg [17:0] data = 18'b111100001111000011; 
//assign clk_42mhz = CLK;
// SB_PLL40_PAD #(
//   .DIVR(4'b0011),
//   .DIVF(7'b0000000),
//   .DIVQ(3'b000),
//   .FILTER_RANGE(3'b001),
//   .FEEDBACK_PATH("SIMPLE"),
//   .DELAY_ADJUSTMENT_MODE_FEEDBACK("FIXED"),
//   .FDA_FEEDBACK(4'b0000),
//   .DELAY_ADJUSTMENT_MODE_RELATIVE("FIXED"),
//   .FDA_RELATIVE(4'b0000),
//   .SHIFTREG_DIV_MODE(2'b00),
//   .PLLOUT_SELECT("GENCLK"),
//   .ENABLE_ICEGATE(1'b0)
// ) usb_pll_inst (
//   .PACKAGEPIN(CLK),
//   .PLLOUTCORE(P1A1),
//   //.PLLOUTGLOBAL(),
//   .EXTFEEDBACK(),
//   .DYNAMICDELAY(),
//   .RESETB(1'b1),
//   .BYPASS(1'b0),
//   .LATCHINPUTVALUE(),
//   //.LOCK(),
//   //.SDI(),
//   //.SDO(),
//   //.SCLK()
// );

/* local parameters */
localparam clk_freq = 12_000_000; // 12MHz
// localparam lr_clk_freq = 3_000_000; // 42MHz
// localparam baud = 57600;
// localparam baud = 115200;
localparam bit_depth = 18;
localparam word_size = 32;
localparam sclk_12mhz_ratio = 4;

clkdiv #(sclk_12mhz_ratio) sclk_clk_div (
  .in(CLK),
  .out(sclk)
);

localparam led_clk_ratio = 3000000;
clkdiv #(led_clk_ratio) led_clk_div (
  .in(sclk),
  .out(LEDR_N)
);

reg rx_ready;
reg [bit_depth - 1: 0] rx_data;
i2s_deserial #(bit_depth, word_size) i2s_rx (
  .BCLK(sclk),
  .SD(mic_data),
  .LRCLK(mic_lr_clk),
  .i2s_data(rx_data),
  .word_ready(rx_ready)
);

reg [bit_depth - 1 : 0] tx_data;
i2s_serialize #(bit_depth, word_size) i2s_tx (
  .BCLK(sclk),
  .sample_data(tx_data),
  .LRCLK(amp_lr_clk),
  .SD(amp_data)
);

//Send the received data immediately back

reg [bit_depth - 1:0] data_buf;
reg data_flag = 0;
// reg data_check_busy = 0;
always @(posedge sclk) begin

  // we got a new data strobe
  // let's save it and set a flag
	if(rx_ready && ~data_flag) begin
    data_buf <= rx_data;
    data_flag <= 1;
    // data_check_busy <= 1;
  end

  // new data flag is set let's try to send it
  if(data_flag) begin

    // First check if the previous transmission is over
    // if(data_check_busy) begin
    //   if(~tx1_busy) begin
    //     data_check_busy <= 0;
    //   end // if(~tx1_busy)

    // end else begin // try to send waiting for busy to go high to make sure
      // if(~tx1_busy) begin
    tx_data <= data_buf;
    data_flag <= 0;
        // tx1_start <= 1'b1;
        // LEDR_N <= ~data_buf[0];
        // LEDG_N <= ~data_buf[1];
  end 
      // else begin // Yey we did it!
      //   tx1_start <= 1'b0;
      //   data_flag <= 0;
      // end
  //   end
  // end
end

// Loopback the TX and RX lines with no processing
// Useful as a sanity check ;-)
// assign TX = RX;

endmodule
