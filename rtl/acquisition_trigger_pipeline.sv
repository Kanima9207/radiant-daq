// RADIANT-DAQ RTL-003: integrated acquisition timebase + threshold trigger pipeline.
//
// Couples the deterministic sample timebase from RTL-001 to the hysteretic
// event detector from RTL-002. On each asserted sample_valid cycle, the trigger
// core observes the pre-increment timebase outputs, so a detected event captures
// metadata for exactly the sample that caused the trigger.
//
// This module is synthesizable. Verification here is simulation-only; no
// physical FPGA timing/resource performance is claimed.

module acquisition_trigger_pipeline #(
    parameter integer SAMPLE_RATE_HZ = 50_000,
    parameter integer SAMPLE_WIDTH   = 16,
    parameter integer INDEX_WIDTH    = 64,
    parameter integer TIME_WIDTH     = 64,
    parameter integer SEQ_WIDTH      = 32,
    parameter integer HOLDOFF_WIDTH  = 32
) (
    input  wire                             clk,
    input  wire                             rst_n,
    input  wire                             sample_valid,
    input  wire                             frame_end,
    input  wire signed [SAMPLE_WIDTH-1:0]  sample_value,
    input  wire signed [SAMPLE_WIDTH-1:0]  threshold_high,
    input  wire signed [SAMPLE_WIDTH-1:0]  threshold_low,
    input  wire [HOLDOFF_WIDTH-1:0]        holdoff_samples,

    output wire [INDEX_WIDTH-1:0]          next_sample_index,
    output wire [TIME_WIDTH-1:0]           next_timestamp_ns,
    output wire [SEQ_WIDTH-1:0]            packet_sequence,

    output wire                             trigger_pulse,
    output wire [INDEX_WIDTH-1:0]          trigger_index,
    output wire [TIME_WIDTH-1:0]           trigger_timestamp_ns,
    output wire signed [SAMPLE_WIDTH-1:0]  trigger_value,
    output wire                             trigger_armed,
    output wire [HOLDOFF_WIDTH-1:0]        holdoff_remaining
);

    acquisition_timebase #(
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ),
        .INDEX_WIDTH(INDEX_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .SEQ_WIDTH(SEQ_WIDTH)
    ) timebase_i (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .frame_end(frame_end),
        .sample_index(next_sample_index),
        .timestamp_ns(next_timestamp_ns),
        .packet_sequence(packet_sequence)
    );

    threshold_trigger #(
        .SAMPLE_WIDTH(SAMPLE_WIDTH),
        .INDEX_WIDTH(INDEX_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .HOLDOFF_WIDTH(HOLDOFF_WIDTH)
    ) trigger_i (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .sample_value(sample_value),
        .threshold_high(threshold_high),
        .threshold_low(threshold_low),
        .holdoff_samples(holdoff_samples),
        .sample_index(next_sample_index),
        .timestamp_ns(next_timestamp_ns),
        .trigger_pulse(trigger_pulse),
        .trigger_index(trigger_index),
        .trigger_timestamp_ns(trigger_timestamp_ns),
        .trigger_value(trigger_value),
        .armed(trigger_armed),
        .holdoff_remaining(holdoff_remaining)
    );

endmodule
