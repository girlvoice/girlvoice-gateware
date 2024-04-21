//
// A generic clock divider
// by Tomek Szczesny 2022
//
// clkdiv divides the frequency of input clock signal by "divider".
// The output signal duty cycle is as near 50% as possible (sometimes less).
// In and out posedges are in sync.
//
//            +------------------+
//            |                  |
//     in --->|      clkdiv      |---> out
//            |                  |
//            +------------------+
//
// Parameters:
// divider - a clock divider.
//
// Ports: 
// in	- Input
// out	- Output
//
`ifndef _clkdiv_v_
`define _clkdiv_v_

module clkdiv(
	input wire in,
	output reg out = 0
);
parameter divider = 2;

reg [$clog2(divider-1):0] clkdiv = 0;

always@(posedge in)
begin
	if (clkdiv >= (divider - 1)) begin
		clkdiv <= 0;
		out <= 1;
	end else begin
		clkdiv <= clkdiv + 1;
		out <= (clkdiv + 1 < (divider/2));
	end
end

endmodule

`endif
