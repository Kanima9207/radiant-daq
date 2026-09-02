// RADIANT-DAQ RTL-002: synthesizable threshold trigger and event detection core.
//
// Detects rising threshold events on signed samples. Hysteresis requires the
// signal to fall to/below threshold_low before re-arming. A sample-count
// holdoff suppresses rapid retriggers. Trigger metadata captures the sample
// index and timestamp presented with the triggering sample.

module threshold_trigger #(
    parameter integer SAMPLE_WIDTH   = 16,
    parameter integer INDEX_WIDTH    = 64,
    parameter integer TIME_WIDTH     = 64,
    parameter integer HOLDOFF_WIDTH  = 32
) (
    input  wire                            clk,
    input  wire                            rst_n,
    input  wire                            sample_valid,
    input  wire signed [SAMPLE_WIDTH-1:0] sample_value,
    input  wire signed [SAMPLE_WIDTH-1:0] threshold_high,
    input  wire signed [SAMPLE_WIDTH-1:0] threshold_low,
    input  wire [HOLDOFF_WIDTH-1:0]       holdoff_samples,
    input  wire [INDEX_WIDTH-1:0]         sample_index,
    input  wire [TIME_WIDTH-1:0]          timestamp_ns,
    output reg                             trigger_pulse,
    output reg  [INDEX_WIDTH-1:0]         trigger_index,
    output reg  [TIME_WIDTH-1:0]          trigger_timestamp_ns,
    output reg  signed [SAMPLE_WIDTH-1:0] trigger_value,
    output reg                             armed,
    output reg  [HOLDOFF_WIDTH-1:0]       holdoff_remaining
);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            trigger_pulse        <= 1'b0;
            trigger_index        <= {INDEX_WIDTH{1'b0}};
            trigger_timestamp_ns <= {TIME_WIDTH{1'b0}};
            trigger_value        <= {SAMPLE_WIDTH{1'b0}};
            armed                <= 1'b1;
            holdoff_remaining    <= {HOLDOFF_WIDTH{1'b0}};
        end else begin
            trigger_pulse <= 1'b0;

            if (sample_valid) begin
                if (holdoff_remaining != {HOLDOFF_WIDTH{1'b0}})
                    holdoff_remaining <= holdoff_remaining - 1'b1;

                if (!armed && sample_value <= threshold_low)
                    armed <= 1'b1;

                if (armed &&
                    holdoff_remaining == {HOLDOFF_WIDTH{1'b0}} &&
                    sample_value >= threshold_high) begin
                    trigger_pulse        <= 1'b1;
                    trigger_index        <= sample_index;
                    trigger_timestamp_ns <= timestamp_ns;
                    trigger_value        <= sample_value;
                    armed                <= 1'b0;
                    holdoff_remaining    <= holdoff_samples;
                end
            end
        end
    end

`ifndef SYNTHESIS
    always @(posedge clk) begin
        if (rst_n && threshold_low > threshold_high)
            $error("threshold_low must be <= threshold_high");
    end
`endif

endmodule
