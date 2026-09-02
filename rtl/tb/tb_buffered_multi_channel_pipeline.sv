`timescale 1ns/1ps

module tb_buffered_multi_channel_pipeline;
    localparam integer CHANNELS = 4;
    localparam integer SAMPLE_WIDTH = 16;
    localparam integer SAMPLE_RATE_HZ = 50_000;
    localparam integer HOLDOFF_WIDTH = 32;
    localparam integer FIFO_DEPTH = 2;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg sample_valid = 1'b0;
    reg frame_end = 1'b0;
    reg event_ready = 1'b0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] sample_values = 0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] threshold_high = 0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] threshold_low = 0;
    reg [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_samples = 0;

    wire [63:0] next_sample_index;
    wire [63:0] next_timestamp_ns;
    wire [31:0] packet_sequence;
    wire [CHANNELS-1:0] pending_events;
    wire event_valid;
    wire [1:0] event_channel;
    wire [63:0] event_index;
    wire [63:0] event_timestamp_ns;
    wire signed [SAMPLE_WIDTH-1:0] event_value;
    wire fifo_empty;
    wire fifo_full;
    wire [1:0] fifo_occupancy;
    wire producer_overflow;
    wire fifo_overflow;

    integer ch;

    buffered_multi_channel_pipeline #(
        .CHANNELS(CHANNELS),
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ),
        .SAMPLE_WIDTH(SAMPLE_WIDTH),
        .HOLDOFF_WIDTH(HOLDOFF_WIDTH),
        .FIFO_DEPTH(FIFO_DEPTH)
    ) dut (
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
        .packet_sequence(packet_sequence),
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

    always #5 clk = ~clk;

    task set_channel_sample;
        input integer channel;
        input signed [SAMPLE_WIDTH-1:0] value;
        begin
            sample_values[channel*SAMPLE_WIDTH +: SAMPLE_WIDTH] = value;
        end
    endtask

    task drive_sample;
        input signed [SAMPLE_WIDTH-1:0] ch0;
        input signed [SAMPLE_WIDTH-1:0] ch1;
        input signed [SAMPLE_WIDTH-1:0] ch2;
        input signed [SAMPLE_WIDTH-1:0] ch3;
        begin
            set_channel_sample(0, ch0);
            set_channel_sample(1, ch1);
            set_channel_sample(2, ch2);
            set_channel_sample(3, ch3);
            sample_valid <= 1'b1;
            @(posedge clk);
            #1;
            sample_valid <= 1'b0;
        end
    endtask

    task idle_cycle;
        begin
            sample_valid <= 1'b0;
            @(posedge clk);
            #1;
        end
    endtask

    task expect_output;
        input [1:0] expected_channel;
        input signed [SAMPLE_WIDTH-1:0] expected_value;
        begin
            if (event_valid !== 1'b1 ||
                event_channel !== expected_channel ||
                event_index !== 64'd1 ||
                event_timestamp_ns !== 64'd20000 ||
                event_value !== expected_value) begin
                $display("FAIL output valid=%0b ch=%0d index=%0d ts=%0d value=%0d occ=%0d pending=%b",
                         event_valid, event_channel, event_index, event_timestamp_ns,
                         event_value, fifo_occupancy, pending_events);
                $fatal(1);
            end
        end
    endtask

    initial begin
        for (ch = 0; ch < CHANNELS; ch = ch + 1) begin
            threshold_high[ch*SAMPLE_WIDTH +: SAMPLE_WIDTH] = 16'sd1000;
            threshold_low[ch*SAMPLE_WIDTH +: SAMPLE_WIDTH] = 16'sd800;
            holdoff_samples[ch*HOLDOFF_WIDTH +: HOLDOFF_WIDTH] = 32'd1;
        end

        repeat (2) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        #1;

        // Sample 0 establishes the below-threshold baseline.
        drive_sample(16'sd100, 16'sd100, 16'sd100, 16'sd100);

        // Sample 1 triggers all four channels simultaneously.
        drive_sample(16'sd1100, 16'sd1200, 16'sd1300, 16'sd1400);

        // Capture all four trigger pulses into producer pending slots.
        idle_cycle();
        if (pending_events !== 4'b1111 || fifo_occupancy !== 0) begin
            $display("FAIL initial pending/fifo pending=%b occ=%0d", pending_events, fifo_occupancy);
            $fatal(1);
        end

        // Downstream is stalled. Fill the two-entry FIFO with CH0 then CH1.
        idle_cycle();
        if (fifo_occupancy !== 1 || pending_events !== 4'b1110) begin
            $display("FAIL first FIFO fill pending=%b occ=%0d", pending_events, fifo_occupancy);
            $fatal(1);
        end
        expect_output(2'd0, 16'sd1100);

        idle_cycle();
        if (!fifo_full || fifo_occupancy !== 2 || pending_events !== 4'b1100) begin
            $display("FAIL FIFO did not become full pending=%b occ=%0d full=%0b",
                     pending_events, fifo_occupancy, fifo_full);
            $fatal(1);
        end
        expect_output(2'd0, 16'sd1100);

        // One more stalled cycle: CH2 must remain pending and the FIFO head must
        // remain stable. No event may be retired while input_ready is blocked.
        idle_cycle();
        if (pending_events !== 4'b1100 || fifo_occupancy !== 2) begin
            $display("FAIL backpressure did not hold producer pending=%b occ=%0d",
                     pending_events, fifo_occupancy);
            $fatal(1);
        end
        expect_output(2'd0, 16'sd1100);

        // Release the consumer. Full FIFO supports simultaneous pop+push, so CH2
        // enters as CH0 leaves, followed by CH3 as CH1 leaves.
        event_ready <= 1'b1;
        idle_cycle();
        if (fifo_occupancy !== 2 || pending_events !== 4'b1000) begin
            $display("FAIL simultaneous pop/push CH2 pending=%b occ=%0d",
                     pending_events, fifo_occupancy);
            $fatal(1);
        end
        expect_output(2'd1, 16'sd1200);

        idle_cycle();
        if (fifo_occupancy !== 2 || pending_events !== 4'b0000) begin
            $display("FAIL simultaneous pop/push CH3 pending=%b occ=%0d",
                     pending_events, fifo_occupancy);
            $fatal(1);
        end
        expect_output(2'd2, 16'sd1300);

        idle_cycle();
        if (fifo_occupancy !== 1) begin
            $display("FAIL drain CH2 occupancy=%0d", fifo_occupancy);
            $fatal(1);
        end
        expect_output(2'd3, 16'sd1400);

        idle_cycle();
        if (!fifo_empty || event_valid !== 1'b0 || fifo_occupancy !== 0) begin
            $display("FAIL FIFO did not drain empty=%0b valid=%0b occ=%0d",
                     fifo_empty, event_valid, fifo_occupancy);
            $fatal(1);
        end

        if (producer_overflow !== 1'b0 || fifo_overflow !== 1'b0) begin
            $display("FAIL overflow producer=%0b fifo=%0b", producer_overflow, fifo_overflow);
            $fatal(1);
        end

        if (next_sample_index !== 64'd2 || next_timestamp_ns !== 64'd40000) begin
            $display("FAIL acquisition timebase index=%0d ts=%0d",
                     next_sample_index, next_timestamp_ns);
            $fatal(1);
        end

        $display("PASS RTL-005 fifo_depth=%0d events=4 order=CH0_CH1_CH2_CH3 backpressure=held",
                 FIFO_DEPTH);
        $finish;
    end
endmodule
