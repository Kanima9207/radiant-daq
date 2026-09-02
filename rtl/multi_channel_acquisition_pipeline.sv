// RADIANT-DAQ RTL-004/005: multi-channel acquisition, triggering, and event arbitration.
//
// One deterministic acquisition timebase is shared by all channels. Each channel
// has an independent threshold/hysteresis/holdoff detector. Triggered events are
// captured into a one-entry pending slot per channel, then serialized by a
// deterministic fixed-priority arbiter (lowest channel number first).
//
// RTL-005 adds a ready/valid handshake at the serialized event output. Pending
// events are retired only when event_valid && event_ready, allowing a downstream
// FIFO or packetizer to apply backpressure without silently losing events.
//
// A sticky event_overflow flag reports when a channel produces a new trigger
// while its previous pending event is still waiting and is not being consumed
// on that cycle. This makes overload visible instead of silently dropping it.
//
// This module is synthesizable. Verification is simulation-only; no physical
// FPGA timing/resource performance is claimed.

module multi_channel_acquisition_pipeline #(
    parameter integer CHANNELS         = 8,
    parameter integer SAMPLE_RATE_HZ   = 50_000,
    parameter integer SAMPLE_WIDTH     = 16,
    parameter integer INDEX_WIDTH      = 64,
    parameter integer TIME_WIDTH       = 64,
    parameter integer SEQ_WIDTH        = 32,
    parameter integer HOLDOFF_WIDTH    = 32,
    parameter integer CHANNEL_ID_WIDTH = (CHANNELS <= 1) ? 1 : $clog2(CHANNELS)
) (
    input  wire                                      clk,
    input  wire                                      rst_n,
    input  wire                                      sample_valid,
    input  wire                                      frame_end,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  sample_values,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  threshold_high,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  threshold_low,
    input  wire        [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_samples,
    input  wire                                      event_ready,

    output wire [INDEX_WIDTH-1:0]                   next_sample_index,
    output wire [TIME_WIDTH-1:0]                    next_timestamp_ns,
    output wire [SEQ_WIDTH-1:0]                     packet_sequence,

    output wire [CHANNELS-1:0]                      channel_trigger_pulses,
    output wire [CHANNELS-1:0]                      pending_events,
    output reg                                       event_valid,
    output reg  [CHANNEL_ID_WIDTH-1:0]              event_channel,
    output reg  [INDEX_WIDTH-1:0]                   event_index,
    output reg  [TIME_WIDTH-1:0]                    event_timestamp_ns,
    output reg  signed [SAMPLE_WIDTH-1:0]           event_value,
    output reg                                       event_overflow
);

    wire [CHANNELS*INDEX_WIDTH-1:0] trigger_indices;
    wire [CHANNELS*TIME_WIDTH-1:0] trigger_timestamps;
    wire signed [CHANNELS*SAMPLE_WIDTH-1:0] trigger_values;
    wire [CHANNELS-1:0] trigger_armed;
    wire [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_remaining;

    reg [CHANNELS-1:0] pending_reg;
    reg [CHANNELS*INDEX_WIDTH-1:0] pending_indices;
    reg [CHANNELS*TIME_WIDTH-1:0] pending_timestamps;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] pending_values;

    reg grant_valid;
    reg [CHANNEL_ID_WIDTH-1:0] grant_channel;

    integer arb_i;
    integer seq_i;

    assign pending_events = pending_reg;

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

    genvar ch;
    generate
        for (ch = 0; ch < CHANNELS; ch = ch + 1) begin : channel_triggers
            threshold_trigger #(
                .SAMPLE_WIDTH(SAMPLE_WIDTH),
                .INDEX_WIDTH(INDEX_WIDTH),
                .TIME_WIDTH(TIME_WIDTH),
                .HOLDOFF_WIDTH(HOLDOFF_WIDTH)
            ) trigger_i (
                .clk(clk),
                .rst_n(rst_n),
                .sample_valid(sample_valid),
                .sample_value(sample_values[ch*SAMPLE_WIDTH +: SAMPLE_WIDTH]),
                .threshold_high(threshold_high[ch*SAMPLE_WIDTH +: SAMPLE_WIDTH]),
                .threshold_low(threshold_low[ch*SAMPLE_WIDTH +: SAMPLE_WIDTH]),
                .holdoff_samples(holdoff_samples[ch*HOLDOFF_WIDTH +: HOLDOFF_WIDTH]),
                .sample_index(next_sample_index),
                .timestamp_ns(next_timestamp_ns),
                .trigger_pulse(channel_trigger_pulses[ch]),
                .trigger_index(trigger_indices[ch*INDEX_WIDTH +: INDEX_WIDTH]),
                .trigger_timestamp_ns(trigger_timestamps[ch*TIME_WIDTH +: TIME_WIDTH]),
                .trigger_value(trigger_values[ch*SAMPLE_WIDTH +: SAMPLE_WIDTH]),
                .armed(trigger_armed[ch]),
                .holdoff_remaining(holdoff_remaining[ch*HOLDOFF_WIDTH +: HOLDOFF_WIDTH])
            );
        end
    endgenerate

    // Fixed-priority arbitration over already-captured pending events.
    always @* begin
        grant_valid   = 1'b0;
        grant_channel = {CHANNEL_ID_WIDTH{1'b0}};

        for (arb_i = 0; arb_i < CHANNELS; arb_i = arb_i + 1) begin
            if (!grant_valid && pending_reg[arb_i]) begin
                grant_valid   = 1'b1;
                grant_channel = arb_i[CHANNEL_ID_WIDTH-1:0];
            end
        end

        event_valid        = grant_valid;
        event_channel      = grant_channel;
        event_index        = {INDEX_WIDTH{1'b0}};
        event_timestamp_ns = {TIME_WIDTH{1'b0}};
        event_value        = {SAMPLE_WIDTH{1'b0}};

        for (arb_i = 0; arb_i < CHANNELS; arb_i = arb_i + 1) begin
            if (grant_valid && grant_channel == arb_i[CHANNEL_ID_WIDTH-1:0]) begin
                event_index = pending_indices[arb_i*INDEX_WIDTH +: INDEX_WIDTH];
                event_timestamp_ns = pending_timestamps[arb_i*TIME_WIDTH +: TIME_WIDTH];
                event_value = pending_values[arb_i*SAMPLE_WIDTH +: SAMPLE_WIDTH];
            end
        end
    end

    // Capture new channel events and retire at most one arbitrated event/cycle.
    // Retirement requires a completed ready/valid handshake. If a channel is
    // being retired while it also produces a new event, the new event replaces
    // the consumed slot with no loss.
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            pending_reg        <= {CHANNELS{1'b0}};
            pending_indices    <= {(CHANNELS*INDEX_WIDTH){1'b0}};
            pending_timestamps <= {(CHANNELS*TIME_WIDTH){1'b0}};
            pending_values     <= {(CHANNELS*SAMPLE_WIDTH){1'b0}};
            event_overflow     <= 1'b0;
        end else begin
            for (seq_i = 0; seq_i < CHANNELS; seq_i = seq_i + 1) begin
                if (grant_valid && event_ready &&
                    grant_channel == seq_i[CHANNEL_ID_WIDTH-1:0]) begin
                    if (channel_trigger_pulses[seq_i]) begin
                        pending_reg[seq_i] <= 1'b1;
                        pending_indices[seq_i*INDEX_WIDTH +: INDEX_WIDTH]
                            <= trigger_indices[seq_i*INDEX_WIDTH +: INDEX_WIDTH];
                        pending_timestamps[seq_i*TIME_WIDTH +: TIME_WIDTH]
                            <= trigger_timestamps[seq_i*TIME_WIDTH +: TIME_WIDTH];
                        pending_values[seq_i*SAMPLE_WIDTH +: SAMPLE_WIDTH]
                            <= trigger_values[seq_i*SAMPLE_WIDTH +: SAMPLE_WIDTH];
                    end else begin
                        pending_reg[seq_i] <= 1'b0;
                    end
                end else if (channel_trigger_pulses[seq_i]) begin
                    if (pending_reg[seq_i]) begin
                        event_overflow <= 1'b1;
                    end else begin
                        pending_reg[seq_i] <= 1'b1;
                        pending_indices[seq_i*INDEX_WIDTH +: INDEX_WIDTH]
                            <= trigger_indices[seq_i*INDEX_WIDTH +: INDEX_WIDTH];
                        pending_timestamps[seq_i*TIME_WIDTH +: TIME_WIDTH]
                            <= trigger_timestamps[seq_i*TIME_WIDTH +: TIME_WIDTH];
                        pending_values[seq_i*SAMPLE_WIDTH +: SAMPLE_WIDTH]
                            <= trigger_values[seq_i*SAMPLE_WIDTH +: SAMPLE_WIDTH];
                    end
                end
            end
        end
    end

`ifndef SYNTHESIS
    initial begin
        if (CHANNELS <= 0) begin
            $error("CHANNELS must be positive");
            $finish;
        end
    end
`endif

endmodule
