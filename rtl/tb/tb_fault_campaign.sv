`timescale 1ns/1ps

module tb_fault_campaign;
    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg packet_valid = 1'b0;
    reg [255:0] packet_data = 256'd0;
    reg clear_safe_request = 1'b0;

    wire packet_ready;
    wire event_valid;
    wire [31:0] event_sequence;
    wire [7:0] event_channel;
    wire [63:0] event_index;
    wire [63:0] event_timestamp_ns;
    wire signed [15:0] event_value;
    wire crc_error_pulse, protocol_error_pulse;
    wire gap_pulse, duplicate_pulse, out_of_order_pulse;
    wire [7:0] fault_score;
    wire [31:0] silence_cycles;
    wire silence_warning, silence_fault;
    wire [1:0] health_state;
    wire diagnostic_request, isolate_link, recovery_request;
    wire safe_state, acquisition_enable;
    wire [31:0] recovery_count, safe_entry_count;

    integer scenarios = 0;
    integer detected = 0;
    integer contained = 0;

    health_monitored_event_packet_receiver #(
        .SILENCE_WARN_CYCLES(4),
        .SILENCE_FAULT_CYCLES(7),
        .WARNING_SCORE(1),
        .DEGRADED_SCORE(2),
        .FAULT_SCORE(4)
    ) rx (
        .clk(clk), .rst_n(rst_n),
        .packet_valid(packet_valid), .packet_ready(packet_ready),
        .packet_data(packet_data),
        .event_valid(event_valid), .event_ready(1'b1),
        .event_sequence(event_sequence), .event_channel(event_channel),
        .event_index(event_index), .event_timestamp_ns(event_timestamp_ns),
        .event_value(event_value),
        .crc_error_pulse(crc_error_pulse),
        .protocol_error_pulse(protocol_error_pulse),
        .gap_pulse(gap_pulse), .duplicate_pulse(duplicate_pulse),
        .out_of_order_pulse(out_of_order_pulse),
        .fault_score(fault_score), .silence_cycles(silence_cycles),
        .silence_warning(silence_warning), .silence_fault(silence_fault),
        .health_state(health_state)
    );

    safe_state_controller #(
        .RECOVERY_PULSE_CYCLES(2),
        .HEALTHY_CLEAR_CYCLES(2),
        .COUNTER_WIDTH(8)
    ) safety (
        .clk(clk), .rst_n(rst_n), .health_state(health_state),
        .clear_safe_request(clear_safe_request),
        .diagnostic_request(diagnostic_request), .isolate_link(isolate_link),
        .recovery_request(recovery_request), .safe_state(safe_state),
        .acquisition_enable(acquisition_enable),
        .recovery_count(recovery_count), .safe_entry_count(safe_entry_count)
    );

    always #5 clk = ~clk;

    function [31:0] crc32_msb;
        input [223:0] data;
        integer i;
        reg [31:0] crc;
        reg feedback;
        begin
            crc = 32'hFFFFFFFF;
            for (i = 223; i >= 0; i = i - 1) begin
                feedback = crc[31] ^ data[i];
                crc = {crc[30:0], 1'b0};
                if (feedback) crc = crc ^ 32'h04C11DB7;
            end
            crc32_msb = crc ^ 32'hFFFFFFFF;
        end
    endfunction

    function [255:0] make_packet;
        input [31:0] seq;
        reg [223:0] payload;
        begin
            payload = {16'h5244, 8'h01, 8'h01, seq, 8'h02, 8'h00,
                       64'd100, 64'd2000000, 16'd1234};
            make_packet = {payload, crc32_msb(payload)};
        end
    endfunction

    task reset_dut;
        begin
            @(negedge clk); rst_n = 1'b0; packet_valid = 1'b0; clear_safe_request = 1'b0;
            repeat (2) @(posedge clk);
            @(negedge clk); rst_n = 1'b1;
            @(posedge clk); #1;
        end
    endtask

    task send_packet;
        input [255:0] p;
        begin
            @(negedge clk); packet_data = p; packet_valid = 1'b1;
            while (!packet_ready) @(negedge clk);
            @(posedge clk); #1;
            @(negedge clk); packet_valid = 1'b0;
            @(posedge clk); #1;
        end
    endtask

    task mark_fault;
        input is_detected;
        input is_contained;
        begin
            scenarios = scenarios + 1;
            if (is_detected) detected = detected + 1;
            if (is_contained) contained = contained + 1;
        end
    endtask

    reg [255:0] p;
    initial begin
        // CLEAN CONTROL: valid packet must pass without fault indication.
        reset_dut();
        send_packet(make_packet(32'd0));
        if (!event_valid && fault_score != 0) $fatal(1, "FAIL clean control");
        if (crc_error_pulse || protocol_error_pulse || gap_pulse || duplicate_pulse || out_of_order_pulse)
            $fatal(1, "FAIL clean false alarm");

        // CRC CORRUPTION.
        reset_dut();
        p = make_packet(32'd0); p[80] = ~p[80];
        send_packet(p);
        mark_fault((fault_score >= 1), diagnostic_request || isolate_link || safe_state);
        if (fault_score < 1) $fatal(1, "FAIL crc detection");

        // PROTOCOL CORRUPTION with a recomputed CRC so format detection is independent.
        reset_dut();
        p = make_packet(32'd0); p[255:240] = 16'h0000; p[31:0] = crc32_msb(p[255:32]);
        send_packet(p);
        mark_fault((fault_score >= 1), diagnostic_request || isolate_link || safe_state);
        if (fault_score < 1) $fatal(1, "FAIL protocol detection");

        // DROP: receiver sees sequence 0 then 2; sequence 1 is missing.
        reset_dut();
        send_packet(make_packet(32'd0));
        send_packet(make_packet(32'd2));
        mark_fault((fault_score >= 2), diagnostic_request || isolate_link || safe_state);
        if (fault_score < 2) $fatal(1, "FAIL drop/gap detection");

        // DUPLICATE.
        reset_dut();
        send_packet(make_packet(32'd5));
        send_packet(make_packet(32'd5));
        mark_fault((fault_score >= 1), diagnostic_request || isolate_link || safe_state);
        if (fault_score < 1) $fatal(1, "FAIL duplicate detection");

        // REORDER: establish 10, jump to 12, then late packet 11.
        reset_dut();
        send_packet(make_packet(32'd10));
        send_packet(make_packet(32'd12));
        send_packet(make_packet(32'd11));
        mark_fault((fault_score >= 4), diagnostic_request || isolate_link || safe_state);
        if (fault_score < 4) $fatal(1, "FAIL reorder detection");
        repeat (2) @(posedge clk); #1;
        if (!safe_state) $fatal(1, "FAIL reorder containment safe state");

        // SILENCE: no packets until watchdog fault threshold is exceeded.
        reset_dut();
        repeat (8) @(posedge clk); #1;
        mark_fault(silence_fault, safe_state || isolate_link || diagnostic_request);
        if (!silence_fault) $fatal(1, "FAIL silence detection");
        repeat (2) @(posedge clk); #1;
        if (!safe_state) $fatal(1, "FAIL silence safe-state containment");

        if (scenarios != 6 || detected != 6 || contained != 6)
            $fatal(1, "FAIL campaign scenarios=%0d detected=%0d contained=%0d", scenarios, detected, contained);

        $display("CAMPAIGN RTL-012 scenarios=%0d detected=%0d contained=%0d detection_pct=100 containment_pct=100", scenarios, detected, contained);
        $display("PASS RTL-012 crc=1 protocol=1 drop=1 duplicate=1 reorder=1 silence=1");
        $finish;
    end
endmodule
