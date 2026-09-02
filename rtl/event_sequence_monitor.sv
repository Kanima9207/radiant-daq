// RADIANT-DAQ RTL-008: event sequence integrity monitor.
//
// Classifies accepted CRC/protocol-valid event packets as in-order, gap/drop,
// duplicate, or late/out-of-order. Sequence arithmetic is modulo 2^32. The
// half-range rule treats forward deltas < 2^31 as gaps and larger deltas as
// late/out-of-order, making normal 0xFFFFFFFF -> 0 wrap-around in-order.
//
// The monitor advances expected_sequence after in-order packets and forward
// gaps. Duplicates and late packets do not move the expected sequence.
//
// This module is synthesizable. Verification is simulation-only.

module event_sequence_monitor (
    input  wire        clk,
    input  wire        rst_n,

    input  wire        event_valid,
    output wire        event_ready,
    input  wire        downstream_ready,
    input  wire [31:0] event_sequence,

    output reg         initialized,
    output reg  [31:0] expected_sequence,

    output reg         in_order_pulse,
    output reg         gap_pulse,
    output reg         duplicate_pulse,
    output reg         out_of_order_pulse,

    output reg  [31:0] in_order_count,
    output reg  [31:0] gap_event_count,
    output reg  [31:0] missing_packet_count,
    output reg  [31:0] duplicate_count,
    output reg  [31:0] out_of_order_count
);

    wire accept_event = event_valid && event_ready;
    wire [31:0] delta = event_sequence - expected_sequence;
    wire [31:0] previous_sequence = expected_sequence - 1'b1;

    assign event_ready = downstream_ready;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            initialized <= 1'b0;
            expected_sequence <= 32'd0;
            in_order_pulse <= 1'b0;
            gap_pulse <= 1'b0;
            duplicate_pulse <= 1'b0;
            out_of_order_pulse <= 1'b0;
            in_order_count <= 32'd0;
            gap_event_count <= 32'd0;
            missing_packet_count <= 32'd0;
            duplicate_count <= 32'd0;
            out_of_order_count <= 32'd0;
        end else begin
            in_order_pulse <= 1'b0;
            gap_pulse <= 1'b0;
            duplicate_pulse <= 1'b0;
            out_of_order_pulse <= 1'b0;

            if (accept_event) begin
                if (!initialized) begin
                    initialized <= 1'b1;
                    expected_sequence <= event_sequence + 1'b1;
                    in_order_pulse <= 1'b1;
                    in_order_count <= in_order_count + 1'b1;
                end else if (event_sequence == expected_sequence) begin
                    expected_sequence <= expected_sequence + 1'b1;
                    in_order_pulse <= 1'b1;
                    in_order_count <= in_order_count + 1'b1;
                end else if (event_sequence == previous_sequence) begin
                    duplicate_pulse <= 1'b1;
                    duplicate_count <= duplicate_count + 1'b1;
                end else if ((delta != 32'd0) && !delta[31]) begin
                    // A forward jump means one or more packets were not seen.
                    gap_pulse <= 1'b1;
                    gap_event_count <= gap_event_count + 1'b1;
                    missing_packet_count <= missing_packet_count + delta;
                    expected_sequence <= event_sequence + 1'b1;
                end else begin
                    out_of_order_pulse <= 1'b1;
                    out_of_order_count <= out_of_order_count + 1'b1;
                end
            end
        end
    end

endmodule
