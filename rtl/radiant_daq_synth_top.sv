// RADIANT-DAQ RTL-014: synthesis-oriented top level.
//
// This wrapper removes the RTL-011 verification fault-injection controls from
// the external interface by tying transport_drop low and transport_xor_mask to
// zero. It exposes the acquisition inputs and compact operational status needed
// for synthesis/elaboration and future board-specific wrappers.
//
// This file establishes synthesis readiness only. It is not evidence of timing
// closure, FPGA programming, physical I/O validation, or radiation tolerance.

module radiant_daq_synth_top #(
    parameter integer CHANNELS       = 4,
    parameter integer SAMPLE_RATE_HZ = 50_000,
    parameter integer SAMPLE_WIDTH   = 16,
    parameter integer HOLDOFF_WIDTH  = 32,
    parameter integer FIFO_DEPTH     = 4
) (
    input  wire                                      clk,
    input  wire                                      rst_n,
    input  wire                                      sample_valid,
    input  wire                                      frame_end,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  sample_values,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  threshold_high,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  threshold_low,
    input  wire        [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_samples,
    input  wire                                      clear_safe_request,

    output wire [1:0]                                health_state,
    output wire [7:0]                                fault_score,
    output wire                                      diagnostic_request,
    output wire                                      isolate_link,
    output wire                                      recovery_request,
    output wire                                      safe_state,
    output wire                                      acquisition_enable,
    output wire [63:0]                               next_sample_index,
    output wire [63:0]                               next_timestamp_ns,
    output wire [31:0]                               event_sequence,
    output wire                                      event_valid
);

    wire [31:0] received_event_sequence;
    wire [7:0] received_event_channel;
    wire [63:0] received_event_index;
    wire [63:0] received_event_timestamp_ns;
    wire signed [15:0] received_event_value;
    wire [31:0] recovery_count;
    wire [31:0] safe_entry_count;
    wire crc_error_pulse;
    wire protocol_error_pulse;
    wire gap_pulse;
    wire duplicate_pulse;
    wire out_of_order_pulse;
    wire [31:0] acquisition_packet_sequence;
    wire [31:0] transmit_event_sequence;
    wire [$clog2(FIFO_DEPTH + 1)-1:0] fifo_occupancy;
    wire producer_overflow;
    wire fifo_overflow;

    fault_tolerant_daq_node #(
        .CHANNELS(CHANNELS),
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ),
        .SAMPLE_WIDTH(SAMPLE_WIDTH),
        .HOLDOFF_WIDTH(HOLDOFF_WIDTH),
        .FIFO_DEPTH(FIFO_DEPTH)
    ) node_i (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .frame_end(frame_end),
        .sample_values(sample_values),
        .threshold_high(threshold_high),
        .threshold_low(threshold_low),
        .holdoff_samples(holdoff_samples),
        .transport_drop(1'b0),
        .transport_xor_mask(256'd0),
        .clear_safe_request(clear_safe_request),
        .received_event_valid(event_valid),
        .received_event_sequence(received_event_sequence),
        .received_event_channel(received_event_channel),
        .received_event_index(received_event_index),
        .received_event_timestamp_ns(received_event_timestamp_ns),
        .received_event_value(received_event_value),
        .health_state(health_state),
        .fault_score(fault_score),
        .diagnostic_request(diagnostic_request),
        .isolate_link(isolate_link),
        .recovery_request(recovery_request),
        .safe_state(safe_state),
        .acquisition_enable(acquisition_enable),
        .recovery_count(recovery_count),
        .safe_entry_count(safe_entry_count),
        .crc_error_pulse(crc_error_pulse),
        .protocol_error_pulse(protocol_error_pulse),
        .gap_pulse(gap_pulse),
        .duplicate_pulse(duplicate_pulse),
        .out_of_order_pulse(out_of_order_pulse),
        .next_sample_index(next_sample_index),
        .next_timestamp_ns(next_timestamp_ns),
        .acquisition_packet_sequence(acquisition_packet_sequence),
        .transmit_event_sequence(transmit_event_sequence),
        .fifo_occupancy(fifo_occupancy),
        .producer_overflow(producer_overflow),
        .fifo_overflow(fifo_overflow)
    );

    assign event_sequence = received_event_sequence;

endmodule
