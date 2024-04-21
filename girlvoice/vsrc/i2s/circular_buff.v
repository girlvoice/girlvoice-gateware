module circular_buff(
    input write [word_size - 1: 0],
    input CLK,
    output reg read [word_size - 1: 0]
)

parameter word_size = 18;
parameter num_words = 32;

reg [word_size - 1:0] buffer[num_words - 1:0]

integer pos = 0;

always @(posedge CLK) begin
    
end