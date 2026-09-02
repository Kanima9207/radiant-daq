`timescale 1ns/1ps

module tb_multi_channel_acquisition_pipeline;
    localparam integer CHANNELS = 4;
    localparam integer SAMPLE_WIDTH = 16;
    localparam integer SAMPLE_RATE_HZ = 50_000;
    localparam integer HOLDOFF_WIDTH = 32;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg sample_valid = 1'b0;
    reg frame_end = 1'b0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] sample_values = 0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] threshold_high = 0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] threshold_low = 0;
    reg [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_samples = 0;

    wire [63:0] next_sample_index;
    wire [63:0] next_timestamp_ns;
    wire [31:0] packet_sequence;
    wire [CHANNELS-1:0] channel_trigger_pulses;
    wire [CHANNELS-1:0] pending_events;
    wire event_valid;
    wire [1:0] event_channel;
    wire [63:0] event_index;
    wire [63:0] event_timestamp_ns;
    wire signed [SAMPLE_WIDTH-1:0] event_value;
    wire event_overflow;

    integer ch;

    multi_channel_acquisition_pipeline #(
        .CHANNELS(CHANNELS),
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ),
        .SAMPLE_WIDTH(SAMPLE_WIDTH),
        .HOLDOFF_WIDTH(HOLDOFF_WIDTH)
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
        .channel_trigger_pulses(channel_trigger_pulses),
        .pending_events(pending_events),
        .event_valid(event_valid),
        .event_channel(event_channel),
        .event_index(event_index),
        .event_timestamp_ns(event_timestamp_ns),
        .event_value(event_value),
        .event_overflow(event_overflow)
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
        input is_frame_end;
        begin
            set_channel_sample(0, ch0);
            set_channel_sample(1, ch1);
            set_channel_sample(2, ch2);
            set_channel_sample(3, ch3);
            frame_end <= is_frame_end;
            sample_valid <= 1'b1;
            @(posedge clk);
            #1;
            sample_valid <= 1'b0;
            frame_end <= 1'b0;
        end
    endtask

    task idle_cycle;
        begin
            sample_valid <= 1'b0;
            frame_end <= 1'b0;
            @(posedge clk);
            #1;
        end
    endtask

    task expect_event;
        input [1:0] expected_channel;
        input [63:0] expected_index;
        input [63:0] expected_timestamp;
        input signed [SAMPLE_WIDTH-1:0] expected_value;
        begin
            if (event_valid !== 1'b1 ||
                event_channel !== expected_channel ||
                event_index !== expected_index ||
                event_timestamp_ns !== expected_timestamp ||
                event_value !== expected_value) begin
                $display("FAIL event valid=%0b ch=%0d index=%0d ts=%0d value=%0d",
                         event_valid, event_channel, event_index,
                         event_timestamp_ns, event_value);
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

        if (next_sample_index !== 0 || next_timestamp_ns !== 0 || packet_sequence !== 0) begin
            $display("FAIL reset timebase state");
            $fatal(1);
        end

        // Sample 0: all channels below threshold.
        drive_sample(16'sd100, 16'sd100, 16'sd100, 16'sd100, 1'b0);
        if (channel_trigger_pulses !== 4'b0000) begin
            $display("FAIL unexpected trigger on sample 0");
            $fatal(1);
        end

        // Sample 1: CH1 and CH3 trigger simultaneously. Both must be retained.
        drive_sample(16'sd100, 16'sd1200, 16'sd100, 16'sd1400, 1'b0);
        if (channel_trigger_pulses !== 4'b1010) begin
            $display("FAIL expected simultaneous CH1/CH3 trigger pulses got=%b",
                     channel_trigger_pulses);
            $fatal(1);
        end

        // Capture trigger pulses into pending slots. Lowest channel wins first.
        idle_cycle();
        if (pending_events !== 4'b1010) begin
            $display("FAIL pending events expected=1010 got=%b", pending_events);
            $fatal(1);
        end
        expect_event(2'd1, 64'd1, 64'd20000, 16'sd1200);

        // Retire CH1. CH3 must remain and become the next event.
        idle_cycle();
        if (pending_events !== 4'b1000) begin
            $display("FAIL CH3 was not preserved pending=%b", pending_events);
            $fatal(1);
        end
        expect_event(2'd3, 64'd1, 64'd20000, 16'sd1400);

        // Retire CH3; event stream becomes empty.
        idle_cycle();
        if (event_valid !== 1'b0 || pending_events !== 4'b0000) begin
            $display("FAIL event queue did not drain pending=%b valid=%0b",
                     pending_events, event_valid);
            $fatal(1);
        end

        // Sample 2: independent CH2 event and end-of-frame sequence increment.
        drive_sample(16'sd100, 16'sd100, 16'sd1300, 16'sd100, 1'b1);
        if (channel_trigger_pulses !== 4'b0100) begin
            $display("FAIL expected CH2 trigger got=%b", channel_trigger_pulses);
            $fatal(1);
        end
        if (packet_sequence !== 32'd1 || next_sample_index !== 64'd3 ||
            next_timestamp_ns !== 64'd60000) begin
            $display("FAIL timebase/sequence index=%0d ts=%0d seq=%0d",
                     next_sample_index, next_timestamp_ns, packet_sequence);
            $fatal(1);
        end

        idle_cycle();
        expect_event(2'd2, 64'd2, 64'd40000, 16'sd1300);

        if (event_overflow !== 1'b0) begin
            $display("FAIL unexpected event overflow");
            $fatal(1);
        end

        idle_cycle();
        if (event_valid !== 1'b0) begin
            $display("FAIL final event did not retire");
            $fatal(1);
        end

        $display("PASS RTL-004 channels=%0d simultaneous_priority=CH1_then_CH3 seq=%0d",
                 CHANNELS, packet_sequence);
        $finish;
    end
endmodule
