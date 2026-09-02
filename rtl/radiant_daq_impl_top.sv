// RADIANT-DAQ RTL-016: compact FPGA implementation wrapper.
//
// The RTL-015 synthesis top intentionally exposes wide parallel configuration
// buses, which is useful for logical mapping but unnecessarily consumes package
// I/O during place-and-route. This wrapper keeps the complete four-channel DAQ
// core while serializing threshold/holdoff configuration through one selected
// channel at a time. Sample data remains four-channel parallel.
//
// This wrapper is for tool-based FPGA implementation analysis only; it is not a
// board interface specification or evidence of physical hardware validation.

module radiant_daq_impl_top #(
    parameter integer CHANNELS       = 4,
    parameter integer SAMPLE_RATE_HZ = 50_000,
    parameter integer SAMPLE_WIDTH   = 16,
    parameter integer HOLDOFF_WIDTH  = 32,
    parameter integer FIFO_DEPTH     = 4
) (
    input  wire                                     clk,
    input  wire                                     rst_n,
    input  wire                                     sample_valid,
    input  wire                                     frame_end,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0] sample_values,

    input  wire                                     cfg_write,
    input  wire [$clog2(CHANNELS)-1:0]              cfg_channel,
    input  wire signed [SAMPLE_WIDTH-1:0]           cfg_threshold_high,
    input  wire signed [SAMPLE_WIDTH-1:0]           cfg_threshold_low,
    input  wire [HOLDOFF_WIDTH-1:0]                 cfg_holdoff_samples,
    input  wire                                     clear_safe_request,

    output wire [1:0]                               health_state,
    output wire [7:0]                               fault_score,
    output wire                                     diagnostic_request,
    output wire                                     isolate_link,
    output wire                                     recovery_request,
    output wire                                     safe_state,
    output wire                                     acquisition_enable,
    output wire                                     event_valid,
    output wire [31:0]                              event_sequence,
    output wire [31:0]                              sample_index_low,
    output wire [31:0]                              timestamp_ns_low
);

    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] threshold_high_regs;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] threshold_low_regs;
    reg        [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_regs;

    wire [63:0] next_sample_index;
    wire [63:0] next_timestamp_ns;

    integer i;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            threshold_high_regs <= {CHANNELS*SAMPLE_WIDTH{1'b0}};
            threshold_low_regs  <= {CHANNELS*SAMPLE_WIDTH{1'b0}};
            holdoff_regs        <= {CHANNELS*HOLDOFF_WIDTH{1'b0}};
        end else if (cfg_write) begin
            threshold_high_regs[cfg_channel*SAMPLE_WIDTH +: SAMPLE_WIDTH] <= cfg_threshold_high;
            threshold_low_regs[cfg_channel*SAMPLE_WIDTH +: SAMPLE_WIDTH]  <= cfg_threshold_low;
            holdoff_regs[cfg_channel*HOLDOFF_WIDTH +: HOLDOFF_WIDTH]      <= cfg_holdoff_samples;
        end
    end

    radiant_daq_synth_top #(
        .CHANNELS(CHANNELS),
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ),
        .SAMPLE_WIDTH(SAMPLE_WIDTH),
        .HOLDOFF_WIDTH(HOLDOFF_WIDTH),
        .FIFO_DEPTH(FIFO_DEPTH)
    ) core_i (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .frame_end(frame_end),
        .sample_values(sample_values),
        .threshold_high(threshold_high_regs),
        .threshold_low(threshold_low_regs),
        .holdoff_samples(holdoff_regs),
        .clear_safe_request(clear_safe_request),
        .health_state(health_state),
        .fault_score(fault_score),
        .diagnostic_request(diagnostic_request),
        .isolate_link(isolate_link),
        .recovery_request(recovery_request),
        .safe_state(safe_state),
        .acquisition_enable(acquisition_enable),
        .next_sample_index(next_sample_index),
        .next_timestamp_ns(next_timestamp_ns),
        .event_sequence(event_sequence),
        .event_valid(event_valid)
    );

    assign sample_index_low  = next_sample_index[31:0];
    assign timestamp_ns_low  = next_timestamp_ns[31:0];

endmodule
