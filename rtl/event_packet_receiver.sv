// RADIANT-DAQ RTL-007: fixed-width event packet receiver with integrity checks.
//
// Validates the RTL-006 256-bit event-frame format, recomputes CRC-32, and
// exposes decoded event metadata through a ready/valid interface. Good packets
// are held under downstream backpressure; malformed packets are consumed and
// rejected immediately with explicit error pulses/counters.
//
// CRC convention matches event_packetizer.sv: polynomial 0x04C11DB7,
// init 0xFFFFFFFF, non-reflected, MSB-first over bits [255:32],
// xorout 0xFFFFFFFF.
//
// This module is synthesizable. Verification is simulation-only.

module event_packet_receiver (
    input  wire                clk,
    input  wire                rst_n,

    input  wire                packet_valid,
    output wire                packet_ready,
    input  wire [255:0]        packet_data,

    output wire                event_valid,
    input  wire                event_ready,
    output wire [31:0]         event_sequence,
    output wire [7:0]          event_channel,
    output wire [63:0]         event_index,
    output wire [63:0]         event_timestamp_ns,
    output wire signed [15:0]  event_value,

    output reg                 crc_error_pulse,
    output reg                 protocol_error_pulse,
    output reg  [31:0]         accepted_packets,
    output reg  [31:0]         rejected_packets,
    output reg  [31:0]         crc_error_count,
    output reg  [31:0]         protocol_error_count
);

    localparam [15:0] MAGIC = 16'h5244;
    localparam [7:0] VERSION = 8'h01;
    localparam [7:0] TYPE_EVENT = 8'h01;

    wire [223:0] payload = packet_data[255:32];
    wire [31:0] received_crc = packet_data[31:0];
    wire [31:0] calculated_crc;

    wire magic_ok = (packet_data[255:240] == MAGIC);
    wire version_ok = (packet_data[239:232] == VERSION);
    wire type_ok = (packet_data[231:224] == TYPE_EVENT);
    wire protocol_ok = magic_ok && version_ok && type_ok;
    wire crc_ok;
    wire packet_good;
    wire accept_bad;
    wire accept_good;

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

    assign calculated_crc = crc32_msb(payload);
    assign crc_ok = (received_crc == calculated_crc);
    assign packet_good = protocol_ok && crc_ok;

    assign event_sequence = packet_data[223:192];
    assign event_channel = packet_data[191:184];
    assign event_index = packet_data[175:112];
    assign event_timestamp_ns = packet_data[111:48];
    assign event_value = packet_data[47:32];

    // Good packets obey downstream backpressure. Bad packets need no output
    // storage, so they can always be consumed/rejected immediately.
    assign event_valid = packet_valid && packet_good;
    assign packet_ready = packet_good ? event_ready : 1'b1;

    assign accept_good = packet_valid && packet_ready && packet_good;
    assign accept_bad = packet_valid && packet_ready && !packet_good;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            crc_error_pulse <= 1'b0;
            protocol_error_pulse <= 1'b0;
            accepted_packets <= 32'd0;
            rejected_packets <= 32'd0;
            crc_error_count <= 32'd0;
            protocol_error_count <= 32'd0;
        end else begin
            crc_error_pulse <= 1'b0;
            protocol_error_pulse <= 1'b0;

            if (accept_good)
                accepted_packets <= accepted_packets + 1'b1;

            if (accept_bad) begin
                rejected_packets <= rejected_packets + 1'b1;

                if (!crc_ok) begin
                    crc_error_pulse <= 1'b1;
                    crc_error_count <= crc_error_count + 1'b1;
                end

                if (!protocol_ok) begin
                    protocol_error_pulse <= 1'b1;
                    protocol_error_count <= protocol_error_count + 1'b1;
                end
            end
        end
    end

endmodule
