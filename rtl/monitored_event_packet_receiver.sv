// RADIANT-DAQ RTL-008: packet receiver with sequence-integrity monitoring.
//
// Composes RTL-007 CRC/protocol validation with event_sequence_monitor. Only
// packets that pass RTL-007 integrity checks reach the sequence monitor.

module monitored_event_packet_receiver (
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

    output wire                crc_error_pulse,
    output wire                protocol_error_pulse,
    output wire [31:0]         accepted_packets,
    output wire [31:0]         rejected_packets,
    output wire [31:0]         crc_error_count,
    output wire [31:0]         protocol_error_count,

    output wire                sequence_initialized,
    output wire [31:0]         expected_sequence,
    output wire                in_order_pulse,
    output wire                gap_pulse,
    output wire                duplicate_pulse,
    output wire                out_of_order_pulse,
    output wire [31:0]         in_order_count,
    output wire [31:0]         gap_event_count,
    output wire [31:0]         missing_packet_count,
    output wire [31:0]         duplicate_count,
    output wire [31:0]         out_of_order_count
);

    wire receiver_event_valid;
    wire monitor_event_ready;
    wire [31:0] receiver_event_sequence;

    event_packet_receiver receiver_i (
        .clk(clk),
        .rst_n(rst_n),
        .packet_valid(packet_valid),
        .packet_ready(packet_ready),
        .packet_data(packet_data),
        .event_valid(receiver_event_valid),
        .event_ready(monitor_event_ready),
        .event_sequence(receiver_event_sequence),
        .event_channel(event_channel),
        .event_index(event_index),
        .event_timestamp_ns(event_timestamp_ns),
        .event_value(event_value),
        .crc_error_pulse(crc_error_pulse),
        .protocol_error_pulse(protocol_error_pulse),
        .accepted_packets(accepted_packets),
        .rejected_packets(rejected_packets),
        .crc_error_count(crc_error_count),
        .protocol_error_count(protocol_error_count)
    );

    event_sequence_monitor sequence_i (
        .clk(clk),
        .rst_n(rst_n),
        .event_valid(receiver_event_valid),
        .event_ready(monitor_event_ready),
        .downstream_ready(event_ready),
        .event_sequence(receiver_event_sequence),
        .initialized(sequence_initialized),
        .expected_sequence(expected_sequence),
        .in_order_pulse(in_order_pulse),
        .gap_pulse(gap_pulse),
        .duplicate_pulse(duplicate_pulse),
        .out_of_order_pulse(out_of_order_pulse),
        .in_order_count(in_order_count),
        .gap_event_count(gap_event_count),
        .missing_packet_count(missing_packet_count),
        .duplicate_count(duplicate_count),
        .out_of_order_count(out_of_order_count)
    );

    assign event_valid = receiver_event_valid;
    assign event_sequence = receiver_event_sequence;

endmodule
