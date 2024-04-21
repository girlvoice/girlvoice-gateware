/* A single delay line tap crudely implemented based on:
 * https://zipcpu.com/dsp/2017/09/15/fastfir.html
 */

module fir_tap (
    input i_clk,
    input reset,
    input signed [IW-1:0] i_sample, // Input sample data
    input i_acc, // Carry in from previous tap
    input wire [(TW-1):0]	     i_h, // Input H/tap coeff
    input                        i_hr, // Reset tap coeff
    output reg signed [OW-1 : 0] o_sample, // Output sample
    output o_acc, // Carry out
    output wire signed [(TW-1):0] o_h // output tap coeff for chaining to next tap
);

parameter IW = 16;
parameter TW = IW;
parameter OW = IW+TW+8;

parameter FIXED_TAP = 1;

reg signed [IW*2:0] acc;
reg signed [IW*2:0] product;

reg signed [IW-1:0] delay;

generate
 if (FIXED_TAP)
    assign o_h = i_h;
else begin
    reg [IW-1: 0] tap;

    initial tap = 0;
    always @(posedge i_clk ) begin
        if (i_hr)
            tap <= i_h;
    end
    assign o_h <= i_h;
end
endgenerate



always @(posedge i_clk ) begin
    if (reset) begin
        product <= 0;
    end else if (i_clk) begin
        product = i_sample * tap;
    end
end

always @(posedge i_clk ) begin
    if (reset) begin
        acc <= 0;
    end else if (i_clk) begin
        acc = i_acc + product;
    end
end

always @(posedge i_clk ) begin
    if (reset) begin
        delay <= 0;
        o_sample <= 0;
    end else if (i_clk) begin
        delay <= i_sample;
        o_sample <= delay;
    end
end




endmodule