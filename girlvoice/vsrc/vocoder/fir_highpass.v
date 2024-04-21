module fir_hp (
    input clk,
    input reset,
    input wire i_tap_wr,
    input wire [TW-1 : 0] i_tap,
    input [IW-1 : 0] i_sample,
    output reg signed [OW-1 : 0] sample_out
);
parameter N;
parameter IW=12;
parameter OW = 2*IW+8;
parameter TW = IW;
parameter FIXED_TAP = 0;

wire [IW-1:0] samples[N:0];
wire [OW-1:0] results[N:0];

wire [TW-1:0] tap [N:0];
wire [TW-1:0] tap_out [N:0];
// wire tap_write = 0;

genvar k;
generate
    if(FIXED_TAP) begin
        initial $readmemh("taps.hex", tap);

        assign tap_write = 1b'0;
    end else begin
        assign tap_write = i_tap_wr;
        assign i_h[0] = i_tap;
    end

endgenerate


genvar j;
generate
    for(j=0; j < N; j = j+1 )
    begin: FILTER

        fir_tap #(
            .FIXED_TAP(FIXED_TAP),
            .IW(IW),
            .OW(OW)

        ) tapj( clk, reset, // clk and reset
                samples[j], results[j], // input sample and input carry/acc sample

                tap[N-1-j], tap_write, samples[j+1], // tap input, tap reset/readwrite, output sample

                results[j+1], tap_out[j]  // carry out, tap output
        );
    if (!FIXED_TAP)
        assign tap[N-1-j] = tap_out[j+1];

    end
endgenerate

assign sample_out = results[N];

endmodule