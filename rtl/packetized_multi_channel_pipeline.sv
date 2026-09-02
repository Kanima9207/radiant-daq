// RADIANT-DAQ RTL-006: buffered multi-channel acquisition pipeline + packetizer.
//
// Integrates RTL-005 event buffering with the fixed 256-bit CRC-protected event
// packet format. Packet backpressure propagates through the event FIFO to the
// trigger arbiter, so accepted event metadata is retained until transport-ready.

module packetized_multi_channel_pipeline #(
    parameter integer CHANNELS          = 8,
    parameter integer SAMPLE_RATE_HZ    = 50_000,
    parameter integer SAMPLE_WIDTH      = 16,
    parameter integer INDEX_WIDTH       = 64,
    parameter integer TIME_WIDTH        = 64,
    parameter integer SEQ_WIDTH         = 32,
    parameter integer HOLDOFF_WIDTH     = 32,
    parameter integer FIFO_DEPTH        = 8,
    parameter integer CHANNEL_ID_WIDTH  = (CHANNELS <= 1) ? 1 : $clog2(CHANNELS),
    parameter integer FIFO_COUNT_WIDTH  = $clog2(FIFO_DEPTH + 1)
) (
    input  wire                                      clk,
    input  wire                                      rst_n,
    input  wire                                      sample_valid,
    input  wire                                      frame_end,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  sample_values,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  threshold_high,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  threshold_low,
    input  wire        [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_samples,

    input  wire                                      packet_ready,
    output wire                                      packet_valid,
    output wire [255:0]                              packet_data,
    output wire [31:0]                               event_packet_sequence,

    output wire [INDEX_WIDTH-1:0]                   next_sample_index,
    output wire [TIME_WIDTH-1:0]                    next_timestamp_ns,
    output wire [SEQ_WIDTH-1:0]                     acquisition_packet_sequence,
    output wire [CHANNELS-1:0]                      pending_events,
    output wire [FIFO_COUNT_WIDTH-1:0]              fifo_occupancy,
    output wire                                      producer_overflow,
    output wire                                      fifo_overflow
);

    wire event_valid;
    wire event_ready;
    wire [CHANNEL_ID_WIDTH-1:0] event_channel;
    wire [INDEX_WIDTH-1:0] event_index;
    wire [TIME_WIDTH-1:0] event_timestamp_ns;
    wire signed [SAMPLE_WIDTH-1:0] event_value;
    wire fifo_empty;
    wire fifo_full;

    wire [7:0] packet_channel = {{(8-CHANNEL_ID_WIDTH){1'b0}}, event_channel};

    buffered_multi_channel_pipeline #(
        .CHANNELS(CHANNELS),
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ),
        .SAMPLE_WIDTH(SAMPLE_WIDTH),
        .INDEX_WIDTH(INDEX_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .SEQ_WIDTH(SEQ_WIDTH),
        .HOLDOFF_WIDTH(HOLDOFF_WIDTH),
        .FIFO_DEPTH(FIFO_DEPTH),
        .CHANNEL_ID_WIDTH(CHANNEL_ID_WIDTH),
        .FIFO_COUNT_WIDTH(FIFO_COUNT_WIDTH)
    ) buffered_i (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .frame_end(frame_end),
        .sample_values(sample_values),
        .threshold_high(threshold_high),
        .threshold_low(threshold_low),
        .holdoff_samples(holdoff_samples),
        .next_sample_index(next_sample_index),
        .next_timestamp_ns(next_timestamp_ns),
        .packet_sequence(acquisition_packet_sequence),
        .pending_events(pending_events),
        .event_valid(event_valid),
        .event_ready(event_ready),
        .event_channel(event_channel),
        .event_index(event_index),
        .event_timestamp_ns(event_timestamp_ns),
        .event_value(event_value),
        .fifo_empty(fifo_empty),
        .fifo_full(fifo_full),
        .fifo_occupancy(fifo_occupancy),
        .producer_overflow(producer_overflow),
        .fifo_overflow(fifo_overflow)
    );

    event_packetizer packetizer_i (
        .clk(clk),
        .rst_n(rst_n),
        .event_valid(event_valid),
        .event_ready(event_ready),
        .event_channel(packet_channel),
        .event_index(event_index),
        .event_timestamp_ns(event_timestamp_ns),
        .event_value(event_value),
        .packet_valid(packet_valid),
        .packet_ready(packet_ready),
        .packet_data(packet_data),
        .packet_sequence(event_packet_sequence)
    );

`ifndef SYNTHESIS
    initial begin
        if (SAMPLE_WIDTH != 16 || INDEX_WIDTH != 64 || TIME_WIDTH != 64) begin
            $error("RTL-006 packet format requires SAMPLE_WIDTH=16, INDEX_WIDTH=64, TIME_WIDTH=64");
            $finish;
        end
        if (CHANNEL_ID_WIDTH > 8) begin
            $error("RTL-006 packet format supports CHANNEL_ID_WIDTH <= 8");
            $finish;
        end
    end
`endif

endmodule
