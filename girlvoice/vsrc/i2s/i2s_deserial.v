

// i2s rx for microphone. Outputs 18 bit vector but the full tx word size is 32 bits
module i2s_deserial(
    input BCLK,
    input SD,
    output reg LRCLK,
    output reg [bit_depth - 1:0] i2s_data,
    output reg word_ready
);

localparam
    READING = 3'b001,
    IDLE    = 3'b010,
    EOW     = 3'b100;

reg [2:0] rx_state = EOW;
parameter bit_depth = 18;
parameter word_size = 32;

integer bit_pos = 0;


always @(negedge BCLK) begin

    if (rx_state[0]) begin
        i2s_data <= {i2s_data[bit_depth-1:1], SD};
    end

end

always @(negedge BCLK) begin
    case(rx_state)
        IDLE:    if(bit_pos >= (word_size - 2) ) rx_state <= EOW;
        READING: if(bit_pos >= (bit_depth - 1) ) rx_state <= IDLE;
        EOW:     rx_state <= READING;
    endcase
end

always @(negedge BCLK) begin
    if (rx_state[2]) begin
            LRCLK <= ~ LRCLK;
            bit_pos <= 0;
            word_ready <= 1;
    end else begin
        bit_pos <= bit_pos + 1;
        word_ready <= 0;
    end

end

endmodule