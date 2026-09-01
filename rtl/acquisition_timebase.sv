// RADIANT-DAQ RTL-001: synthesizable acquisition timebase and sequence core.
//
// Generates exact floor(sample_index * 1e9 / SAMPLE_RATE_HZ) timestamps using
// an integer quotient/remainder accumulator. This matches the software DAQ
// timestamp convention without requiring a divider in the sample datapath.
// No physical FPGA timing performance is claimed until synthesis/hardware tests.

module acquisition_timebase #(
    parameter integer SAMPLE_RATE_HZ = 50_000,
    parameter integer INDEX_WIDTH    = 64,
    parameter integer TIME_WIDTH     = 64,
    parameter integer SEQ_WIDTH      = 32
) (
    input  wire                      clk,
    input  wire                      rst_n,
    input  wire                      sample_valid,
    input  wire                      frame_end,
    output reg  [INDEX_WIDTH-1:0]    sample_index,
    output reg  [TIME_WIDTH-1:0]     timestamp_ns,
    output reg  [SEQ_WIDTH-1:0]      sequence
);

    localparam integer NS_PER_SECOND = 1_000_000_000;
    localparam integer NS_STEP       = NS_PER_SECOND / SAMPLE_RATE_HZ;
    localparam integer NS_REM        = NS_PER_SECOND % SAMPLE_RATE_HZ;

    // The remainder is always in [0, SAMPLE_RATE_HZ-1]. A 64-bit register
    // keeps this implementation simple and portable across simulators/tools.
    reg [63:0] remainder;
    reg [63:0] remainder_sum;

    always @* begin
        remainder_sum = remainder + NS_REM;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            sample_index <= {INDEX_WIDTH{1'b0}};
            timestamp_ns <= {TIME_WIDTH{1'b0}};
            sequence     <= {SEQ_WIDTH{1'b0}};
            remainder    <= 64'd0;
        end else if (sample_valid) begin
            sample_index <= sample_index + {{(INDEX_WIDTH-1){1'b0}}, 1'b1};

            if (remainder_sum >= SAMPLE_RATE_HZ) begin
                timestamp_ns <= timestamp_ns + NS_STEP + 1;
                remainder    <= remainder_sum - SAMPLE_RATE_HZ;
            end else begin
                timestamp_ns <= timestamp_ns + NS_STEP;
                remainder    <= remainder_sum;
            end

            if (frame_end)
                sequence <= sequence + {{(SEQ_WIDTH-1){1'b0}}, 1'b1};
        end
    end

`ifndef SYNTHESIS
    initial begin
        if (SAMPLE_RATE_HZ <= 0 || SAMPLE_RATE_HZ > NS_PER_SECOND) begin
            $error("SAMPLE_RATE_HZ must be in [1, 1e9]");
            $finish;
        end
    end
`endif

endmodule
