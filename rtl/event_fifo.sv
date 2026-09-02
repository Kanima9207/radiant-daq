// RADIANT-DAQ RTL-005: synthesizable event FIFO with ready/valid backpressure.
//
// Buffers serialized event metadata between the multi-channel trigger arbiter and
// a slower downstream packetizer/transport. Simultaneous pop+push is supported,
// including when the FIFO is full, so sustained one-event-per-cycle flow does
// not incur unnecessary bubbles.
//
// fifo_overflow is a sticky internal safety diagnostic. Normal ready/valid
// backpressure (input_valid high while input_ready low) is not an overflow; the
// upstream source is expected to hold its event stable until accepted.

module event_fifo #(
    parameter integer DEPTH            = 8,
    parameter integer CHANNEL_ID_WIDTH = 3,
    parameter integer INDEX_WIDTH      = 64,
    parameter integer TIME_WIDTH       = 64,
    parameter integer SAMPLE_WIDTH     = 16,
    parameter integer PTR_WIDTH        = (DEPTH <= 1) ? 1 : $clog2(DEPTH),
    parameter integer COUNT_WIDTH      = $clog2(DEPTH + 1)
) (
    input  wire                            clk,
    input  wire                            rst_n,

    input  wire                            input_valid,
    output wire                            input_ready,
    input  wire [CHANNEL_ID_WIDTH-1:0]     input_channel,
    input  wire [INDEX_WIDTH-1:0]          input_index,
    input  wire [TIME_WIDTH-1:0]           input_timestamp_ns,
    input  wire signed [SAMPLE_WIDTH-1:0]  input_value,

    output wire                            output_valid,
    input  wire                            output_ready,
    output wire [CHANNEL_ID_WIDTH-1:0]     output_channel,
    output wire [INDEX_WIDTH-1:0]          output_index,
    output wire [TIME_WIDTH-1:0]           output_timestamp_ns,
    output wire signed [SAMPLE_WIDTH-1:0]  output_value,

    output wire                            empty,
    output wire                            full,
    output reg  [COUNT_WIDTH-1:0]          occupancy,
    output reg                             fifo_overflow
);

    reg [CHANNEL_ID_WIDTH-1:0] channel_mem [0:DEPTH-1];
    reg [INDEX_WIDTH-1:0] index_mem [0:DEPTH-1];
    reg [TIME_WIDTH-1:0] timestamp_mem [0:DEPTH-1];
    reg signed [SAMPLE_WIDTH-1:0] value_mem [0:DEPTH-1];

    reg [PTR_WIDTH-1:0] write_ptr;
    reg [PTR_WIDTH-1:0] read_ptr;

    wire do_pop;
    wire do_push;

    assign empty = (occupancy == 0);
    assign full = (occupancy == DEPTH);
    assign output_valid = !empty;

    // A simultaneous pop frees a slot on the same edge, so the source may push
    // even when the FIFO is currently full if the consumer is ready.
    assign input_ready = !full || (output_valid && output_ready);
    assign do_pop = output_valid && output_ready;
    assign do_push = input_valid && input_ready;

    assign output_channel = channel_mem[read_ptr];
    assign output_index = index_mem[read_ptr];
    assign output_timestamp_ns = timestamp_mem[read_ptr];
    assign output_value = value_mem[read_ptr];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            write_ptr <= {PTR_WIDTH{1'b0}};
            read_ptr <= {PTR_WIDTH{1'b0}};
            occupancy <= {COUNT_WIDTH{1'b0}};
            fifo_overflow <= 1'b0;
        end else begin
            // This condition should be unreachable because input_ready prevents
            // a push into a full FIFO unless a simultaneous pop occurs.
            if (do_push && full && !do_pop)
                fifo_overflow <= 1'b1;

            if (do_push) begin
                channel_mem[write_ptr] <= input_channel;
                index_mem[write_ptr] <= input_index;
                timestamp_mem[write_ptr] <= input_timestamp_ns;
                value_mem[write_ptr] <= input_value;

                if (write_ptr == DEPTH-1)
                    write_ptr <= {PTR_WIDTH{1'b0}};
                else
                    write_ptr <= write_ptr + 1'b1;
            end

            if (do_pop) begin
                if (read_ptr == DEPTH-1)
                    read_ptr <= {PTR_WIDTH{1'b0}};
                else
                    read_ptr <= read_ptr + 1'b1;
            end

            case ({do_push, do_pop})
                2'b10: occupancy <= occupancy + 1'b1;
                2'b01: occupancy <= occupancy - 1'b1;
                default: occupancy <= occupancy;
            endcase
        end
    end

`ifndef SYNTHESIS
    initial begin
        if (DEPTH <= 0) begin
            $error("DEPTH must be positive");
            $finish;
        end
    end
`endif

endmodule
