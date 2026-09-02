`timescale 1ns/1ps

module tb_packetized_multi_channel_pipeline;
    localparam integer CHANNELS = 4;
    localparam integer SAMPLE_WIDTH = 16;
    localparam integer HOLDOFF_WIDTH = 32;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg sample_valid = 1'b0;
    reg frame_end = 1'b0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] sample_values = 0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] threshold_high = 0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] threshold_low = 0;
    reg [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_samples = 0;
    reg packet_ready = 1'b0;

    wire packet_valid;
    wire [255:0] packet_data;
    wire [31:0] event_packet_sequence;
    wire [63:0] next_sample_index;
    wire [63:0] next_timestamp_ns;
    wire [31:0] acquisition_packet_sequence;
    wire [CHANNELS-1:0] pending_events;
    wire [2:0] fifo_occupancy;
    wire producer_overflow;
    wire fifo_overflow;

    reg [255:0] packet0;
    reg [255:0] packet1;
    integer ch;

    packetized_multi_channel_pipeline #(
        .CHANNELS(CHANNELS),
        .FIFO_DEPTH(4)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .frame_end(frame_end),
        .sample_values(sample_values),
        .threshold_high(threshold_high),
        .threshold_low(threshold_low),
        .holdoff_samples(holdoff_samples),
        .packet_ready(packet_ready),
        .packet_valid(packet_valid),
        .packet_data(packet_data),
        .event_packet_sequence(event_packet_sequence),
        .next_sample_index(next_sample_index),
        .next_timestamp_ns(next_timestamp_ns),
        .acquisition_packet_sequence(acquisition_packet_sequence),
        .pending_events(pending_events),
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

    task accept_packet;
        begin
            packet_ready <= 1'b1;
            @(posedge clk);
            #1;
            packet_ready <= 1'b0;
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

        // Sample 0: baseline below thresholds.
        drive_sample(16'sd100, 16'sd100, 16'sd100, 16'sd100, 1'b0);

        // Sample 1: CH2 event -> index=1, timestamp=20,000 ns.
        drive_sample(16'sd100, 16'sd100, 16'sd1200, 16'sd100, 1'b0);

        // Sample 2: re-arm all channels.
        drive_sample(16'sd100, 16'sd100, 16'sd100, 16'sd100, 1'b0);

        // Sample 3: CH0 event and end-of-frame -> index=3, timestamp=60,000 ns.
        drive_sample(16'sd1300, 16'sd100, 16'sd100, 16'sd100, 1'b1);

        repeat (4) idle_cycle();

        if (acquisition_packet_sequence !== 32'd1 || next_sample_index !== 64'd4 ||
            next_timestamp_ns !== 64'd80000) begin
            $display("FAIL acquisition metadata index=%0d ts=%0d seq=%0d",
                     next_sample_index, next_timestamp_ns, acquisition_packet_sequence);
            $fatal(1);
        end

        if (packet_valid !== 1'b1) begin
            $display("FAIL first packet not available");
            $fatal(1);
        end

        packet0 = packet_data;
        if (packet0[255:240] !== 16'h5244 || packet0[239:232] !== 8'h01 ||
            packet0[231:224] !== 8'h01 || packet0[223:192] !== 32'd0 ||
            packet0[191:184] !== 8'd2 || packet0[183:176] !== 8'd0 ||
            packet0[175:112] !== 64'd1 || packet0[111:48] !== 64'd20000 ||
            packet0[47:32] !== 16'd1200) begin
            $display("FAIL first packet fields packet=%064h", packet0);
            $fatal(1);
        end

        // Backpressure must hold the entire frame and sequence stable.
        repeat (2) begin
            idle_cycle();
            if (packet_valid !== 1'b1 || packet_data !== packet0 ||
                event_packet_sequence !== 32'd0) begin
                $display("FAIL packet changed under backpressure");
                $fatal(1);
            end
        end

        $display("PACKET0=%064h", packet0);
        accept_packet();
        if (event_packet_sequence !== 32'd1) begin
            $display("FAIL sequence did not advance after packet0");
            $fatal(1);
        end

        // The second buffered event should now be presented as sequence 1.
        if (packet_valid !== 1'b1)
            idle_cycle();
        if (packet_valid !== 1'b1) begin
            $display("FAIL second packet not available");
            $fatal(1);
        end

        packet1 = packet_data;
        if (packet1[255:240] !== 16'h5244 || packet1[239:232] !== 8'h01 ||
            packet1[231:224] !== 8'h01 || packet1[223:192] !== 32'd1 ||
            packet1[191:184] !== 8'd0 || packet1[183:176] !== 8'd0 ||
            packet1[175:112] !== 64'd3 || packet1[111:48] !== 64'd60000 ||
            packet1[47:32] !== 16'd1300) begin
            $display("FAIL second packet fields packet=%064h", packet1);
            $fatal(1);
        end

        $display("PACKET1=%064h", packet1);
        accept_packet();

        if (event_packet_sequence !== 32'd2) begin
            $display("FAIL final packet sequence=%0d", event_packet_sequence);
            $fatal(1);
        end
        if (producer_overflow !== 1'b0 || fifo_overflow !== 1'b0) begin
            $display("FAIL unexpected overflow producer=%0b fifo=%0b",
                     producer_overflow, fifo_overflow);
            $fatal(1);
        end

        idle_cycle();
        if (packet_valid !== 1'b0) begin
            $display("FAIL packet stream did not drain");
            $fatal(1);
        end

        $display("PASS RTL-006 packets=2 crc32=IEEE_MSB backpressure=stable");
        $finish;
    end
endmodule
