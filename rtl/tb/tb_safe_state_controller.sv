`timescale 1ns/1ps

module tb_safe_state_controller;
    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg [1:0] health_state = 2'b00;
    reg clear_safe_request = 1'b0;

    wire diagnostic_request;
    wire isolate_link;
    wire recovery_request;
    wire safe_state;
    wire acquisition_enable;
    wire [31:0] recovery_count;
    wire [31:0] safe_entry_count;

    localparam [1:0] HEALTHY  = 2'b00;
    localparam [1:0] WARNING  = 2'b01;
    localparam [1:0] DEGRADED = 2'b10;
    localparam [1:0] FAULT    = 2'b11;

    safe_state_controller #(
        .RECOVERY_PULSE_CYCLES(2),
        .HEALTHY_CLEAR_CYCLES(3),
        .COUNTER_WIDTH(8)
    ) dut (
        .clk(clk), .rst_n(rst_n), .health_state(health_state),
        .clear_safe_request(clear_safe_request),
        .diagnostic_request(diagnostic_request), .isolate_link(isolate_link),
        .recovery_request(recovery_request), .safe_state(safe_state),
        .acquisition_enable(acquisition_enable),
        .recovery_count(recovery_count), .safe_entry_count(safe_entry_count)
    );

    always #5 clk = ~clk;

    task set_health;
        input [1:0] state;
        begin
            @(negedge clk);
            health_state = state;
            @(posedge clk); #1;
        end
    endtask

    initial begin
        repeat (2) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk); #1;

        if (safe_state || !acquisition_enable || isolate_link)
            $fatal(1, "FAIL reset healthy policy");

        set_health(WARNING);
        if (!diagnostic_request || isolate_link || recovery_request || safe_state)
            $fatal(1, "FAIL warning policy");

        set_health(DEGRADED);
        if (!diagnostic_request || !isolate_link || !recovery_request || safe_state)
            $fatal(1, "FAIL degraded containment");
        if (recovery_count != 32'd1)
            $fatal(1, "FAIL recovery count %0d", recovery_count);

        // Recovery request is bounded to two cycles and does not retrigger while
        // the same DEGRADED episode persists.
        @(posedge clk); #1;
        if (!recovery_request) $fatal(1, "FAIL recovery pulse cycle 2");
        @(posedge clk); #1;
        if (recovery_request) $fatal(1, "FAIL recovery pulse did not end");
        if (recovery_count != 32'd1) $fatal(1, "FAIL recovery retriggered");

        set_health(FAULT);
        if (!safe_state || acquisition_enable || !isolate_link)
            $fatal(1, "FAIL fault safe-state entry");
        if (safe_entry_count != 32'd1)
            $fatal(1, "FAIL safe entry count");

        // A transient healthy state is insufficient, even with clear asserted.
        @(negedge clk);
        health_state = HEALTHY;
        clear_safe_request = 1'b1;
        repeat (2) @(posedge clk);
        #1;
        if (!safe_state) $fatal(1, "FAIL safe state cleared too early");

        // After the configured healthy qualification, explicit clear releases it.
        repeat (2) @(posedge clk);
        #1;
        if (safe_state) $fatal(1, "FAIL qualified safe-state clear");
        if (!acquisition_enable || isolate_link)
            $fatal(1, "FAIL post-clear acquisition policy");
        clear_safe_request = 1'b0;

        // Leaving DEGRADED arms a future recovery episode.
        set_health(DEGRADED);
        if (!recovery_request || recovery_count != 32'd2)
            $fatal(1, "FAIL second recovery episode");
        set_health(HEALTHY);

        $display("PASS RTL-010 recoveries=2 safe_entries=1 qualified_clear=3");
        $finish;
    end
endmodule
