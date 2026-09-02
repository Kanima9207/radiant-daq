// RADIANT-DAQ RTL-009: integrity-monitored receiver with link health watchdog.
//
// Composes RTL-007/008 receive integrity with link_health_monitor. Every
// consumed packet resets the silence watchdog, while CRC/protocol/sequence
// anomalies contribute to the fault score. In-order traffic heals that score.

module health_monitored_event_packet_receiver #(
    parameter integer SILENCE_WARN_CYCLES  = 8,
    parameter integer SILENCE_FAULT_CYCLES = 16,
    parameter integer WARNING_SCORE        = 1,
    parameter integer DEGRADED_SCORE       = 3,
    parameter integer FAULT_SCORE          = 5
) (
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
    output wire                gap_pulse,
    output wire                duplicate_pulse,
    output wire                out_of_order_pulse,

    output wire [7:0]          fault_score,
    output wire [31:0]         silence_cycles,
    output wire                silence_warning,
    output wire                silence_fault,
    output wire [1:0]          health_state
);

    wire [31:0] accepted_packets;
    wire [31:0] rejected_packets;
    wire [31:0] crc_error_count;
    wire [31:0] protocol_error_count;
    wire sequence_initialized;
    wire [31:0] expected_sequence;
    wire in_order_pulse;
    wire [31:0] in_order_count;
    wire [31:0] gap_event_count;
    wire [31:0] missing_packet_count;
    wire [31:0] duplicate_count;
    wire [31:0] out_of_order_count;

    wire packet_activity_pulse = packet_valid && packet_ready;

    monitored_event_packet_receiver receiver_i (
        .clk(clk),
        .rst_n(rst_n),
        .packet_valid(packet_valid),
        .packet_ready(packet_ready),
        .packet_data(packet_data),
        .event_valid(event_valid),
        .event_ready(event_ready),
        .event_sequence(event_sequence),
        .event_channel(event_channel),
        .event_index(event_index),
        .event_timestamp_ns(event_timestamp_ns),
        .event_value(event_value),
        .crc_error_pulse(crc_error_pulse),
        .protocol_error_pulse(protocol_error_pulse),
        .accepted_packets(accepted_packets),
        .rejected_packets(rejected_packets),
        .crc_error_count(crc_error_count),
        .protocol_error_count(protocol_error_count),
        .sequence_initialized(sequence_initialized),
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

    link_health_monitor #(
        .SILENCE_WARN_CYCLES(SILENCE_WARN_CYCLES),
        .SILENCE_FAULT_CYCLES(SILENCE_FAULT_CYCLES),
        .WARNING_SCORE(WARNING_SCORE),
        .DEGRADED_SCORE(DEGRADED_SCORE),
        .FAULT_SCORE(FAULT_SCORE)
    ) health_i (
        .clk(clk),
        .rst_n(rst_n),
        .packet_activity_pulse(packet_activity_pulse),
        .good_event_pulse(in_order_pulse),
        .crc_error_pulse(crc_error_pulse),
        .protocol_error_pulse(protocol_error_pulse),
        .gap_pulse(gap_pulse),
        .duplicate_pulse(duplicate_pulse),
        .out_of_order_pulse(out_of_order_pulse),
        .fault_score(fault_score),
        .silence_cycles(silence_cycles),
        .silence_warning(silence_warning),
        .silence_fault(silence_fault),
        .health_state(health_state)
    );

endmodule
