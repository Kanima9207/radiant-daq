`timescale 1ns/1ps

module tb_fault_tolerant_daq_node;
    localparam integer CHANNELS = 4;
    localparam integer SAMPLE_WIDTH = 16;
    localparam integer HOLDOFF_WIDTH = 32;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg sample_valid = 1'b0;
    reg frame_end = 1'b0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] sample_values = '0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] threshold_high = '0;
    reg signed [CHANNELS*SAMPLE_WIDTH-1:0] threshold_low = '0;
    reg [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_samples = '0;
    reg transport_drop = 1'b0;
    reg [255:0] transport_xor_mask = 256'd0;
    reg clear_safe_request = 1'b0;

    wire received_event_valid;
    wire [31:0] received_event_sequence;
    wire [7:0] received_event_channel;
    wire [63:0] received_event_index;
    wire [63:0] received_event_timestamp_ns;
    wire signed [15:0] received_event_value;
    wire [1:0] health_state;
    wire [7:0] fault_score;
    wire diagnostic_request;
    wire isolate_link;
    wire recovery_request;
    wire safe_state;
    wire acquisition_enable;
    wire [31:0] recovery_count;
    wire [31:0] safe_entry_count;
    wire crc_error_pulse;
    wire protocol_error_pulse;
    wire gap_pulse;
    wire duplicate_pulse;
    wire out_of_order_pulse;
    wire [63:0] next_sample_index;
    wire [63:0] next_timestamp_ns;
    wire [31:0] acquisition_packet_sequence;
    wire [31:0] transmit_event_sequence;
    wire [2:0] fifo_occupancy;
    wire producer_overflow;
    wire fifo_overflow;

    integer crc_errors_seen = 0;
    integer protocol_errors_seen = 0;
    integer timeout;
    reg [63:0] frozen_sample_index;

    fault_tolerant_daq_node #(
        .CHANNELS(CHANNELS),
        .FIFO_DEPTH(4),
        .SILENCE_WARN_CYCLES(100),
        .SILENCE_FAULT_CYCLES(200),
        .WARNING_SCORE(1),
        .DEGRADED_SCORE(3),
        .FAULT_SCORE(5),
        .RECOVERY_PULSE_CYCLES(2),
        .HEALTHY_CLEAR_CYCLES(3)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .sample_valid(sample_valid), .frame_end(frame_end),
        .sample_values(sample_values), .threshold_high(threshold_high),
        .threshold_low(threshold_low), .holdoff_samples(holdoff_samples),
        .transport_drop(transport_drop), .transport_xor_mask(transport_xor_mask),
        .clear_safe_request(clear_safe_request),
        .received_event_valid(received_event_valid),
        .received_event_sequence(received_event_sequence),
        .received_event_channel(received_event_channel),
        .received_event_index(received_event_index),
        .received_event_timestamp_ns(received_event_timestamp_ns),
        .received_event_value(received_event_value),
        .health_state(health_state), .fault_score(fault_score),
        .diagnostic_request(diagnostic_request), .isolate_link(isolate_link),
        .recovery_request(recovery_request), .safe_state(safe_state),
        .acquisition_enable(acquisition_enable),
        .recovery_count(recovery_count), .safe_entry_count(safe_entry_count),
        .crc_error_pulse(crc_error_pulse),
        .protocol_error_pulse(protocol_error_pulse),
        .gap_pulse(gap_pulse), .duplicate_pulse(duplicate_pulse),
        .out_of_order_pulse(out_of_order_pulse),
        .next_sample_index(next_sample_index),
        .next_timestamp_ns(next_timestamp_ns),
        .acquisition_packet_sequence(acquisition_packet_sequence),
        .transmit_event_sequence(transmit_event_sequence),
        .fifo_occupancy(fifo_occupancy),
        .producer_overflow(producer_overflow), .fifo_overflow(fifo_overflow)
    );

    always #5 clk = ~clk;

    always @(posedge clk) begin
        if (crc_error_pulse)
            crc_errors_seen = crc_errors_seen + 1;
        if (protocol_error_pulse)
            protocol_errors_seen = protocol_errors_seen + 1;
    end

    task drive_ch0_sample;
        input signed [15:0] value;
        begin
            @(negedge clk);
            sample_values = '0;
            sample_values[15:0] = value;
            sample_valid = 1'b1;
            @(posedge clk); #1;
            sample_valid = 1'b0;
        end
    endtask

    task wait_for_received_event;
        begin
            timeout = 0;
            while (!received_event_valid && timeout < 30) begin
                @(posedge clk); #1;
                timeout = timeout + 1;
            end
            if (!received_event_valid)
                $fatal(1, "FAIL timeout waiting for received event");
        end
    endtask

    task wait_for_protocol_error;
        begin
            timeout = 0;
            while (!protocol_error_pulse && timeout < 30) begin
                @(posedge clk); #1;
                timeout = timeout + 1;
            end
            if (!protocol_error_pulse)
                $fatal(1, "FAIL timeout waiting for protocol error");
        end
    endtask

    initial begin
        integer ch;
        for (ch = 0; ch < CHANNELS; ch = ch + 1) begin
            threshold_high[ch*SAMPLE_WIDTH +: SAMPLE_WIDTH] = 16'sd1000;
            threshold_low[ch*SAMPLE_WIDTH +: SAMPLE_WIDTH] = 16'sd800;
            holdoff_samples[ch*HOLDOFF_WIDTH +: HOLDOFF_WIDTH] = 32'd1;
        end

        repeat (2) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk); #1;

        if (!acquisition_enable || safe_state || health_state != 2'b00)
            $fatal(1, "FAIL initial node state");

        // Sample 0 below threshold, sample 1 crosses CH0 threshold.
        drive_ch0_sample(16'sd0);
        drive_ch0_sample(16'sd1200);
        wait_for_received_event();

        if (received_event_sequence != 32'd0 || received_event_channel != 8'd0 ||
            received_event_index != 64'd1 ||
            received_event_timestamp_ns != 64'd20000 ||
            received_event_value != 16'sd1200)
            $fatal(1, "FAIL clean event metadata seq=%0d ch=%0d idx=%0d ts=%0d val=%0d",
                   received_event_sequence, received_event_channel,
                   received_event_index, received_event_timestamp_ns,
                   received_event_value);

        // Rearm trigger, then corrupt one magic-header bit in transit. Because the
        // CRC covers the header, this must raise both protocol and CRC errors.
        drive_ch0_sample(16'sd0);
        transport_xor_mask[255] = 1'b1;
        drive_ch0_sample(16'sd1300);
        wait_for_protocol_error();
        transport_xor_mask = 256'd0;

        // First corrupted packet adds score 3 -> DEGRADED and requests recovery.
        repeat (2) @(posedge clk); #1;
        if (fault_score < 8'd3 || health_state < 2'b10)
            $fatal(1, "FAIL first fault escalation score=%0d state=%0d", fault_score, health_state);

        // Rearm and inject the same transport corruption a second time.
        drive_ch0_sample(16'sd0);
        transport_xor_mask[255] = 1'b1;
        drive_ch0_sample(16'sd1400);
        wait_for_protocol_error();
        transport_xor_mask = 256'd0;

        timeout = 0;
        while (!safe_state && timeout < 20) begin
            @(posedge clk); #1;
            timeout = timeout + 1;
        end
        if (!safe_state)
            $fatal(1, "FAIL safe state not entered score=%0d state=%0d", fault_score, health_state);
        if (health_state != 2'b11 || acquisition_enable || !isolate_link)
            $fatal(1, "FAIL safe containment policy");
        if (safe_entry_count != 32'd1)
            $fatal(1, "FAIL safe entry count %0d", safe_entry_count);
        if (crc_errors_seen != 2 || protocol_errors_seen != 2)
            $fatal(1, "FAIL integrity counts crc=%0d protocol=%0d",
                   crc_errors_seen, protocol_errors_seen);
        if (producer_overflow || fifo_overflow)
            $fatal(1, "FAIL unexpected event overflow");

        // Safe-state containment must block new acquisition samples entirely.
        frozen_sample_index = next_sample_index;
        drive_ch0_sample(16'sd0);
        drive_ch0_sample(16'sd1500);
        repeat (4) @(posedge clk); #1;
        if (next_sample_index != frozen_sample_index)
            $fatal(1, "FAIL acquisition advanced in safe state before=%0d after=%0d",
                   frozen_sample_index, next_sample_index);

        $display("PASS RTL-011 clean_event=1 crc_errors=2 protocol_errors=2 safe_entries=1 acquisition_blocked=1");
        $finish;
    end
endmodule
