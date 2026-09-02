`timescale 1ns/1ps

module tb_event_sequence_monitor;
    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg event_valid = 1'b0;
    reg downstream_ready = 1'b1;
    reg [31:0] event_sequence = 32'd0;

    wire event_ready;
    wire initialized;
    wire [31:0] expected_sequence;
    wire in_order_pulse;
    wire gap_pulse;
    wire duplicate_pulse;
    wire out_of_order_pulse;
    wire [31:0] in_order_count;
    wire [31:0] gap_event_count;
    wire [31:0] missing_packet_count;
    wire [31:0] duplicate_count;
    wire [31:0] out_of_order_count;

    event_sequence_monitor dut (
        .clk(clk), .rst_n(rst_n),
        .event_valid(event_valid), .event_ready(event_ready),
        .downstream_ready(downstream_ready), .event_sequence(event_sequence),
        .initialized(initialized), .expected_sequence(expected_sequence),
        .in_order_pulse(in_order_pulse), .gap_pulse(gap_pulse),
        .duplicate_pulse(duplicate_pulse), .out_of_order_pulse(out_of_order_pulse),
        .in_order_count(in_order_count), .gap_event_count(gap_event_count),
        .missing_packet_count(missing_packet_count), .duplicate_count(duplicate_count),
        .out_of_order_count(out_of_order_count)
    );

    always #5 clk = ~clk;

    task send_sequence;
        input [31:0] seq;
        begin
            @(negedge clk);
            event_sequence = seq;
            event_valid = 1'b1;
            @(posedge clk);
            #1;
            event_valid = 1'b0;
        end
    endtask

    initial begin
        repeat (2) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk); #1;

        // First packet establishes the stream at sequence 10.
        send_sequence(32'd10);
        if (!in_order_pulse || expected_sequence != 32'd11) $fatal(1, "FAIL init");

        send_sequence(32'd11);
        if (!in_order_pulse || expected_sequence != 32'd12) $fatal(1, "FAIL in-order");

        // Jump 12 -> 14: sequences 12 and 13 are missing (delta=2).
        send_sequence(32'd14);
        if (!gap_pulse || missing_packet_count != 32'd2 || expected_sequence != 32'd15)
            $fatal(1, "FAIL gap missing=%0d expected=%0d", missing_packet_count, expected_sequence);

        // Repeating the most recently accepted sequence is a duplicate.
        send_sequence(32'd14);
        if (!duplicate_pulse || duplicate_count != 32'd1 || expected_sequence != 32'd15)
            $fatal(1, "FAIL duplicate");

        // Older sequence is late/out-of-order and must not move expected state.
        send_sequence(32'd12);
        if (!out_of_order_pulse || out_of_order_count != 32'd1 || expected_sequence != 32'd15)
            $fatal(1, "FAIL out-of-order");

        send_sequence(32'd15);
        if (!in_order_pulse || expected_sequence != 32'd16) $fatal(1, "FAIL recovery");

        // Backpressure: an event presented while not ready must not be counted.
        @(negedge clk);
        downstream_ready = 1'b0;
        event_sequence = 32'd16;
        event_valid = 1'b1;
        repeat (3) @(posedge clk);
        #1;
        if (expected_sequence != 32'd16 || in_order_count != 32'd3)
            $fatal(1, "FAIL backpressure changed state");
        downstream_ready = 1'b1;
        @(posedge clk); #1;
        event_valid = 1'b0;
        if (!in_order_pulse || expected_sequence != 32'd17) $fatal(1, "FAIL backpressure release");

        if (in_order_count != 32'd4 || gap_event_count != 32'd1 ||
            missing_packet_count != 32'd2 || duplicate_count != 32'd1 ||
            out_of_order_count != 32'd1)
            $fatal(1, "FAIL counters order=%0d gaps=%0d missing=%0d dup=%0d ooo=%0d",
                   in_order_count, gap_event_count, missing_packet_count,
                   duplicate_count, out_of_order_count);

        $display("PASS RTL-008 in_order=4 gaps=1 missing=2 duplicates=1 out_of_order=1");
        $finish;
    end
endmodule
