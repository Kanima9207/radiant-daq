`timescale 1ns/1ps

module tb_acquisition_trigger_pipeline;
    localparam integer SAMPLE_RATE_HZ = 50_000;
    localparam integer FRAME_SAMPLES  = 4;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg sample_valid = 1'b0;
    reg frame_end = 1'b0;
    reg signed [15:0] sample_value = 16'sd0;
    reg signed [15:0] threshold_high = 16'sd1000;
    reg signed [15:0] threshold_low  = 16'sd500;
    reg [31:0] holdoff_samples = 32'd2;

    wire [63:0] next_sample_index;
    wire [63:0] next_timestamp_ns;
    wire [31:0] packet_sequence;
    wire trigger_pulse;
    wire [63:0] trigger_index;
    wire [63:0] trigger_timestamp_ns;
    wire signed [15:0] trigger_value;
    wire trigger_armed;
    wire [31:0] holdoff_remaining;

    integer accepted;
    integer trigger_count;

    acquisition_trigger_pipeline #(
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .frame_end(frame_end),
        .sample_value(sample_value),
        .threshold_high(threshold_high),
        .threshold_low(threshold_low),
        .holdoff_samples(holdoff_samples),
        .next_sample_index(next_sample_index),
        .next_timestamp_ns(next_timestamp_ns),
        .packet_sequence(packet_sequence),
        .trigger_pulse(trigger_pulse),
        .trigger_index(trigger_index),
        .trigger_timestamp_ns(trigger_timestamp_ns),
        .trigger_value(trigger_value),
        .trigger_armed(trigger_armed),
        .holdoff_remaining(holdoff_remaining)
    );

    always #5 clk = ~clk;

    task drive_sample;
        input signed [15:0] value;
        input integer expect_trigger;
        input integer expected_trigger_index;
        begin
            @(negedge clk);
            sample_value = value;
            sample_valid = 1'b1;
            frame_end = ((accepted % FRAME_SAMPLES) == FRAME_SAMPLES - 1);
            @(posedge clk);
            #1;

            accepted = accepted + 1;

            if (trigger_pulse !== expect_trigger[0]) begin
                $display("FAIL trigger pulse sample=%0d expected=%0d got=%0d", accepted-1, expect_trigger, trigger_pulse);
                $fatal(1);
            end

            if (expect_trigger) begin
                trigger_count = trigger_count + 1;
                if (trigger_index !== expected_trigger_index) begin
                    $display("FAIL trigger index expected=%0d got=%0d", expected_trigger_index, trigger_index);
                    $fatal(1);
                end
                if (trigger_timestamp_ns !== ((expected_trigger_index * 64'd1000000000) / SAMPLE_RATE_HZ)) begin
                    $display("FAIL trigger timestamp index=%0d got=%0d", expected_trigger_index, trigger_timestamp_ns);
                    $fatal(1);
                end
                if (trigger_value !== value) begin
                    $display("FAIL trigger value expected=%0d got=%0d", value, trigger_value);
                    $fatal(1);
                end
            end

            if (next_sample_index !== accepted) begin
                $display("FAIL next sample index expected=%0d got=%0d", accepted, next_sample_index);
                $fatal(1);
            end
            if (next_timestamp_ns !== ((accepted * 64'd1000000000) / SAMPLE_RATE_HZ)) begin
                $display("FAIL next timestamp accepted=%0d got=%0d", accepted, next_timestamp_ns);
                $fatal(1);
            end
            if (packet_sequence !== (accepted / FRAME_SAMPLES)) begin
                $display("FAIL packet sequence accepted=%0d expected=%0d got=%0d", accepted, accepted / FRAME_SAMPLES, packet_sequence);
                $fatal(1);
            end
        end
    endtask

    initial begin
        accepted = 0;
        trigger_count = 0;

        repeat (2) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        #1;

        if (next_sample_index !== 0 || next_timestamp_ns !== 0 || packet_sequence !== 0) begin
            $display("FAIL reset state");
            $fatal(1);
        end

        // Sample 0: below threshold.
        drive_sample(16'sd100, 0, 0);

        // Sample 1: first event. Metadata must identify index 1 / 20 us.
        drive_sample(16'sd1200, 1, 1);

        // Sample 2: still high; hysteresis and holdoff suppress retrigger.
        drive_sample(16'sd1300, 0, 0);

        // Insert invalid/stalled cycles. They must not advance timebase or holdoff.
        @(negedge clk);
        sample_valid = 1'b0;
        frame_end = 1'b0;
        sample_value = 16'sd0;
        repeat (3) begin
            @(posedge clk);
            #1;
            if (next_sample_index !== 3 || next_timestamp_ns !== 64'd60000) begin
                $display("FAIL stall advanced timebase index=%0d timestamp=%0d", next_sample_index, next_timestamp_ns);
                $fatal(1);
            end
            if (holdoff_remaining !== 1) begin
                $display("FAIL stall consumed holdoff got=%0d", holdoff_remaining);
                $fatal(1);
            end
        end

        // Sample 3: go below low threshold; re-arm and finish first frame.
        drive_sample(16'sd400, 0, 0);

        // Sample 4: second event after re-arm + holdoff expiration.
        drive_sample(16'sd1500, 1, 4);

        // More nominal samples prove counters continue coherently.
        drive_sample(16'sd300, 0, 0);
        drive_sample(16'sd200, 0, 0);
        drive_sample(16'sd100, 0, 0);

        if (trigger_count !== 2) begin
            $display("FAIL expected 2 triggers got=%0d", trigger_count);
            $fatal(1);
        end

        if (packet_sequence !== 2) begin
            $display("FAIL expected 2 completed frames got=%0d", packet_sequence);
            $fatal(1);
        end

        $display("PASS RTL-003 samples=%0d triggers=%0d frames=%0d", accepted, trigger_count, packet_sequence);
        $finish;
    end
endmodule
