// RADIANT-DAQ RTL-006: fixed-width event packetizer with CRC-32 protection.
//
// Converts one buffered event into a deterministic 256-bit transport frame.
// The packet remains stable under downstream backpressure and the event sequence
// advances only when a packet is accepted (packet_valid && packet_ready).
//
// Packet layout, MSB first:
//   [255:240] magic            = 16'h5244 ("RD")
//   [239:232] version          = 8'h01
//   [231:224] type             = 8'h01 (event)
//   [223:192] event_sequence   = 32-bit monotonically increasing counter
//   [191:184] channel_id       = 8-bit channel identifier
//   [183:176] flags            = 8'h00 (reserved)
//   [175:112] sample_index     = 64-bit acquisition sample index
//   [111:48]  timestamp_ns     = 64-bit timestamp
//   [47:32]   sample_value     = signed 16-bit sample, raw two's-complement bits
//   [31:0]    crc32            = CRC-32 over bits [255:32]
//
// CRC convention: polynomial 0x04C11DB7, init 0xFFFFFFFF, non-reflected,
// MSB-first over the 224 payload bits, xorout 0xFFFFFFFF.
//
// This module is synthesizable. Verification is simulation-only; no physical
// link throughput or FPGA timing/resource performance is claimed.

module event_packetizer (
    input  wire                clk,
    input  wire                rst_n,

    input  wire                event_valid,
    output wire                event_ready,
    input  wire [7:0]          event_channel,
    input  wire [63:0]         event_index,
    input  wire [63:0]         event_timestamp_ns,
    input  wire signed [15:0]  event_value,

    output wire                packet_valid,
    input  wire                packet_ready,
    output wire [255:0]        packet_data,
    output wire [31:0]         packet_sequence
);

    localparam [15:0] MAGIC = 16'h5244;
    localparam [7:0] VERSION = 8'h01;
    localparam [7:0] TYPE_EVENT = 8'h01;

    reg [31:0] sequence_reg;
    wire [223:0] payload;
    wire [31:0] payload_crc;

    function [31:0] crc32_msb;
        input [223:0] data;
        integer i;
        reg [31:0] crc;
        reg feedback;
        begin
            crc = 32'hFFFFFFFF;
            for (i = 223; i >= 0; i = i - 1) begin
                feedback = crc[31] ^ data[i];
                crc = {crc[30:0], 1'b0};
                if (feedback)
                    crc = crc ^ 32'h04C11DB7;
            end
            crc32_msb = crc ^ 32'hFFFFFFFF;
        end
    endfunction

    assign payload = {
        MAGIC,
        VERSION,
        TYPE_EVENT,
        sequence_reg,
        event_channel,
        8'h00,
        event_index,
        event_timestamp_ns,
        event_value
    };

    assign payload_crc = crc32_msb(payload);
    assign packet_data = {payload, payload_crc};

    assign packet_valid = event_valid;
    assign event_ready = packet_ready;
    assign packet_sequence = sequence_reg;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            sequence_reg <= 32'd0;
        else if (packet_valid && packet_ready)
            sequence_reg <= sequence_reg + 1'b1;
    end

endmodule
