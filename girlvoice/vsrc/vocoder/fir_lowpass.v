/* FIR low-pass moving average filter
 * iCE40 only supports up to 16x16 bit DSP blocks so I will have to downscale the input mic data at some point
 */


module fir_lp (
    input clk,
    input reset,
    input [bit_depth-1:0] sample_in,
    output reg signed [bit_depth-1 : 0] sample_out
);

function integer log2(input integer v); begin log2=0; while(v >> log2) log2 = log2 + 1; end endfunction

parameter N = 55;
parameter bit_depth = 16;
// parameter word_size = 32;

localparam logN = log2(N);

integer i;

reg signed [bit_depth-1:0] fifo[N-1:0];

reg signed [bit_depth-1:0] delay_sample;
reg signed [bit_depth:0] sub;
reg signed [bit_depth+logN-1:0] acc;

// reg last_sample[bit_depth-1:0] = fifo[N-1]

always @(posedge clk ) begin
    if (reset) begin
        delay_sample <= 0;
    end else begin
        delay_sample <= sample_in;
    end
end

always @(posedge clk ) begin
    if (reset) begin
        for( i= 0; i<N; i = i+1 ) begin
            fifo[i] <= 0;
        end
    end else begin
        for( i= N - 1; i>0; i = i-1 ) begin
            fifo[i] <= fifo[i - 1];
        end
        fifo[0] <= sample_in;

    end
end


always @(posedge clk) begin
    if (reset) begin
        sub <= 0;
    end else begin
        sub <= delay_sample - fifo[N-1];
    end
end

always @(posedge clk ) begin
    if (reset) begin
        acc <= 0;
    end else begin
        acc <= acc + { {(logN-1){sub[bit_depth]}}, sub };
    end
end

always @(posedge clk ) begin
    if (reset) begin
        sample_out <= 0;
    end else begin
        sample_out <= acc[bit_depth+logN-1:logN];
    end

end



endmodule