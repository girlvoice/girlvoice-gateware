
module i2s_serialize (
    input BCLK,
    input [bit_depth - 1:0] sample_data,
    output reg LRCLK,
    output reg SD
    );

localparam 
    WRITING = 3'b001,
    IDLE    = 3'b010,
    EOW     = 3'b110;

//wire tx_ready;

//assign tx_ready = LRCLK;

reg [2:0] tx_state = EOW;
parameter bit_depth = 18;
parameter word_size = 32;


integer bit_pos = 0;

reg [bit_depth-1:0] tx_shift = 0;


// tx_state[1] high when idle, low when writing

always @(negedge BCLK) begin
    
    if (tx_state[0]) begin
        SD <= tx_shift[bit_depth - 1];
        tx_shift <= (tx_shift << 1);
    end
    if (tx_state[1]) begin
        SD <= 0;
    end
    if (tx_state[2]) begin
        tx_shift <= sample_data;
        LRCLK <= ~ LRCLK;
        bit_pos <= 0;
    end else
        bit_pos <= bit_pos + 1;

end

always @(negedge BCLK) begin
    case(tx_state)
        IDLE:    if(bit_pos >= (word_size - 2) ) tx_state <= EOW;
        WRITING: if(bit_pos >= (bit_depth - 1) ) tx_state <= IDLE;
        EOW:     tx_state <= WRITING;
    endcase
end

endmodule