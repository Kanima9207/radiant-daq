`timescale 1ns/1ps

module tb_link_health_monitor;
    localparam [1:0] HEALTHY  = 2'b00;
    localparam [1:0] WARNING  = 2'b01;
    localparam [1:0] DEGRADED = 2'b10;
    localparam [1:0] FAULT    = 2'b11;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg packet_activity_pulse = 1'b0;
    reg good_event_pulse = 1'b0;
    reg crc_error_pulse = 1'b0;
    reg protocol_error_pulse = 1'b0;
    reg gap_pulse = 1'b0;
    reg duplicate_pulse = 1'b0;
    reg out_of_order_pulse = 1'b0;

    wire [7:0] fault_score;
    wire [31:0] silence_cycles;
    wire silence_warning;
    wire silence_fault;
    wire [1:0] health_state;

    link_health_monitor #(
        .SILENCE_WARN_CYCLES(3),
        .SILENCE_FAULT_CYCLES(6),
        .WARNING_SCORE(1),
        .DEGRADED_SCORE(3),
        .FAULT_SCORE(5)
    ) dut (
        .clk(clk), .rst_n(rst_n),
        .packet_activity_pulse(packet_activity_pulse),
        .good_event_pulse(good_event_pulse),
        .crc_error_pulse(crc_error_pulse),
        .protocol_error_pulse(protocol_error_pulse),
        .gap_pulse(gap_pulse),
        .duplicate_pulse(duplicate_pulse),
        .out_of_order_pulse(out_of_order_pulse),
        .fault_score(fault_score), .silence_cycles(silence_cycles),
        .silence_warning(silence_warning), .silence_fault(silence_fault),
        .health_state(health_state)
    );

    always #5 clk = ~clk;

    task idle_cycle;
        begin
            @(negedge clk);
            packet_activity_pulse = 1'b0;
            good_event_pulse = 1'b0;
            @(posedge clk); #1;
        end
    endtask

    task pulse_activity;
        begin
            @(negedge clk);
            packet_activity_pulse = 1'b1;
            @(posedge clk); #1;
            packet_activity_pulse = 1'b0;
        end
    endtask

    task pulse_crc;
        begin
            @(negedge clk);
            packet_activity_pulse = 1'b1;
            crc_error_pulse = 1'b1;
            @(posedge clk); #1;
            packet_activity_pulse = 1'b0;
            crc_error_pulse = 1'b0;
        end
    endtask

    task pulse_protocol;
        begin
            @(negedge clk);
            packet_activity_pulse = 1'b1;
            protocol_error_pulse = 1'b1;
            @(posedge clk); #1;
            packet_activity_pulse = 1'b0;
            protocol_error_pulse = 1'b0;
        end
    endtask

    task pulse_gap;
        begin
            @(negedge clk);
            packet_activity_pulse = 1'b1;
            gap_pulse = 1'b1;
            @(posedge clk); #1;
            packet_activity_pulse = 1'b0;
            gap_pulse = 1'b0;
        end
    endtask

    task pulse_duplicate;
        begin
            @(negedge clk);
            packet_activity_pulse = 1'b1;
            duplicate_pulse = 1'b1;
            @(posedge clk); #1;
            packet_activity_pulse = 1'b0;
            duplicate_pulse = 1'b0;
        end
    endtask

    task pulse_out_of_order;
        begin
            @(negedge clk);
            packet_activity_pulse = 1'b1;
            out_of_order_pulse = 1'b1;
            @(posedge clk); #1;
            packet_activity_pulse = 1'b0;
            out_of_order_pulse = 1'b0;
        end
    endtask

    task pulse_good;
        begin
            @(negedge clk);
            packet_activity_pulse = 1'b1;
            good_event_pulse = 1'b1;
            @(posedge clk); #1;
            packet_activity_pulse = 1'b0;
            good_event_pulse = 1'b0;
        end
    endtask

    initial begin
        repeat (2) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk); #1;

        if (health_state != HEALTHY || fault_score != 0 || silence_cycles != 1)
            $fatal(1, "FAIL initial health state=%0d score=%0d silence=%0d",
                   health_state, fault_score, silence_cycles);

        // Silence watchdog: warning at 3 cycles, fault at 6.
        idle_cycle();
        idle_cycle();
        if (health_state != WARNING || !silence_warning || silence_fault)
            $fatal(1, "FAIL silence warning state=%0d silence=%0d", health_state, silence_cycles);

        repeat (3) idle_cycle();
        if (health_state != FAULT || !silence_fault || silence_cycles != 6)
            $fatal(1, "FAIL silence fault state=%0d silence=%0d", health_state, silence_cycles);

        pulse_activity();
        if (health_state != HEALTHY || silence_cycles != 0)
            $fatal(1, "FAIL silence recovery state=%0d silence=%0d", health_state, silence_cycles);

        // Fault-score escalation: CRC +1, protocol +2, gap +2.
        pulse_crc();
        if (fault_score != 1 || health_state != WARNING)
            $fatal(1, "FAIL crc escalation score=%0d state=%0d", fault_score, health_state);

        pulse_protocol();
        if (fault_score != 3 || health_state != DEGRADED)
            $fatal(1, "FAIL protocol escalation score=%0d state=%0d", fault_score, health_state);

        pulse_gap();
        if (fault_score != 5 || health_state != FAULT)
            $fatal(1, "FAIL gap escalation score=%0d state=%0d", fault_score, health_state);

        // Five clean in-order events heal back to healthy.
        repeat (5) pulse_good();
        if (fault_score != 0 || health_state != HEALTHY)
            $fatal(1, "FAIL score recovery score=%0d state=%0d", fault_score, health_state);

        // Exercise duplicate and late/out-of-order sequence penalties too.
        pulse_duplicate();
        if (fault_score != 1 || health_state != WARNING)
            $fatal(1, "FAIL duplicate penalty");
        pulse_out_of_order();
        if (fault_score != 3 || health_state != DEGRADED)
            $fatal(1, "FAIL out-of-order penalty score=%0d state=%0d", fault_score, health_state);

        repeat (3) pulse_good();
        if (fault_score != 0 || health_state != HEALTHY)
            $fatal(1, "FAIL final recovery");

        $display("PASS RTL-009 silence_warn=3 silence_fault=6 score_fault=5 recovery=healthy");
        $finish;
    end
endmodule
