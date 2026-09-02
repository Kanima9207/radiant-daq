// RADIANT-DAQ RTL-005: buffered multi-channel acquisition/event pipeline.
//
// Integrates RTL-004 event arbitration with a parameterized event FIFO. The
// FIFO's input_ready feeds back into the arbiter so pending events are retained
// until accepted. Downstream logic consumes events using a standard ready/valid
// handshake.

module buffered_multi_channel_pipeline #(
    parameter integer CHANNELS         = 8,
    parameter integer SAMPLE_RATE_HZ   = 50_000,
    parameter integer SAMPLE_WIDTH     = 16,
    parameter integer INDEX_WIDTH      = 64,
    parameter integer TIME_WIDTH       = 64,
    parameter integer SEQ_WIDTH        = 32,
    parameter integer HOLDOFF_WIDTH    = 32,
    parameter integer FIFO_DEPTH       = 8,
    parameter integer CHANNEL_ID_WIDTH = (CHANNELS <= 1) ? 1 : $clog2(CHANNELS),
    parameter integer FIFO_COUNT_WIDTH = $clog2(FIFO_DEPTH + 1)
) (
    input  wire                                      clk,
    input  wire                                      rst_n,
    input  wire                                      sample_valid,
    input  wire                                      frame_end,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  sample_values,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  threshold_high,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  threshold_low,
    input  wire        [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_samples,

    output wire [INDEX_WIDTH-1:0]                   next_sample_index,
    output wire [TIME_WIDTH-1:0]                    next_timestamp_ns,
    output wire [SEQ_WIDTH-1:0]                     packet_sequence,
    output wire [CHANNELS-1:0]                      pending_events,

    output wire                                      event_valid,
    input  wire                                      event_ready,
    output wire [CHANNEL_ID_WIDTH-1:0]              event_channel,
    output wire [INDEX_WIDTH-1:0]                   event_index,
    output wire [TIME_WIDTH-1:0]                    event_timestamp_ns,
    output wire signed [SAMPLE_WIDTH-1:0]           event_value,

    output wire                                      fifo_empty,
    output wire                                      fifo_full,
    output wire [FIFO_COUNT_WIDTH-1:0]              fifo_occupancy,
    output wire                                      producer_overflow,
    output wire                                      fifo_overflow
);

    wire [CHANNELS-1:0] channel_trigger_pulses;
    wire producer_event_valid;
    wire producer_event_ready;
    wire [CHANNEL_ID_WIDTH-1:0] producer_event_channel;
    wire [INDEX_WIDTH-1:0] producer_event_index;
    wire [TIME_WIDTH-1:0] producer_event_timestamp_ns;
    wire signed [SAMPLE_WIDTH-1:0] producer_event_value;

    multi_channel_acquisition_pipeline #(
        .CHANNELS(CHANNELS),
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ),
        .SAMPLE_WIDTH(SAMPLE_WIDTH),
        .INDEX_WIDTH(INDEX_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .SEQ_WIDTH(SEQ_WIDTH),
        .HOLDOFF_WIDTH(HOLDOFF_WIDTH),
        .CHANNEL_ID_WIDTH(CHANNEL_ID_WIDTH)
    ) producer_i (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .frame_end(frame_end),
        .sample_values(sample_values),
        .threshold_high(threshold_high),
        .threshold_low(threshold_low),
        .holdoff_samples(holdoff_samples),
        .event_ready(producer_event_ready),
        .next_sample_index(next_sample_index),
        .next_timestamp_ns(next_timestamp_ns),
        .packet_sequence(packet_sequence),
        .channel_trigger_pulses(channel_trigger_pulses),
        .pending_events(pending_events),
        .event_valid(producer_event_valid),
        .event_channel(producer_event_channel),
        .event_index(producer_event_index),
        .event_timestamp_ns(producer_event_timestamp_ns),
        .event_value(producer_event_value),
        .event_overflow(producer_overflow)
    );

    event_fifo #(
        .DEPTH(FIFO_DEPTH),
        .CHANNEL_ID_WIDTH(CHANNEL_ID_WIDTH),
        .INDEX_WIDTH(INDEX_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .SAMPLE_WIDTH(SAMPLE_WIDTH)
    ) fifo_i (
        .clk(clk),
        .rst_n(rst_n),
        .input_valid(producer_event_valid),
        .input_ready(producer_event_ready),
        .input_channel(producer_event_channel),
        .input_index(producer_event_index),
        .input_timestamp_ns(producer_event_timestamp_ns),
        .input_value(producer_event_value),
        .output_valid(event_valid),
        .output_ready(event_ready),
        .output_channel(event_channel),
        .output_index(event_index),
        .output_timestamp_ns(event_timestamp_ns),
        .output_value(event_value),
        .empty(fifo_empty),
        .full(fifo_full),
        .occupancy(fifo_occupancy),
        .fifo_overflow(fifo_overflow)
    );

endmodule
