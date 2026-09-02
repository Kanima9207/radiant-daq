`timescale 1ns/1ps

module tb_threshold_trigger;
    localparam integer SAMPLE_WIDTH = 16;
    localparam integer HOLDOFF = 3;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg sample_valid = 1'b0;
    reg signed [SAMPLE_WIDTH-1:0] sample_value = 0;
    reg signed [SAMPLE_WIDTH-1:0] threshold_high = 1000;
    reg signed [SAMPLE_WIDTH-1:0] threshold_low = 800;
    reg [31:0] holdoff_samples = HOLDOFF;
    reg [63:0] sample_index = 0;
    reg [63:0] timestamp_ns = 0;

    wire trigger_pulse;
    wire [63:0] trigger_index;
    wire [63:0] trigger_timestamp_ns;
    wire signed [SAMPLE_WIDTH-1:0] trigger_value;
    wire armed;
    wire [31:0] holdoff_remaining;

    integer trigger_count;

    threshold_trigger dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .sample_value(sample_value),
        .threshold_high(threshold_high),
        .threshold_low(threshold_low),
        .holdoff_samples(holdoff_samples),
        .sample_index(sample_index),
        .timestamp_ns(timestamp_ns),
        .trigger_pulse(trigger_pulse),
        .trigger_index(trigger_index),
        .trigger_timestamp_ns(trigger_timestamp_ns),
        .trigger_value(trigger_value),
        .armed(armed),
        .holdoff_remaining(holdoff_remaining)
    );

    always #5 clk = ~clk;

    task drive_sample;
        input signed [SAMPLE_WIDTH-1:0] value;
        input [63:0] idx;
        input [63:0] ts;
        begin
            sample_value <= value;
            sample_index <= idx;
            timestamp_ns <= ts;
            sample_valid <= 1'b1;
            @(posedge clk);
            #1;
            if (trigger_pulse)
                trigger_count = trigger_count + 1;
            sample_valid <= 1'b0;
        end
    endtask

    task expect_no_trigger;
        begin
            if (trigger_pulse !== 1'b0) begin
                $display("FAIL unexpected trigger index=%0d value=%0d", trigger_index, trigger_value);
                $fatal(1);
            end
        end
    endtask

    initial begin
        trigger_count = 0;

        repeat (2) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        #1;

        if (armed !== 1'b1) begin
            $display("FAIL trigger did not start armed");
            $fatal(1);
        end

        // Below threshold: no event.
        drive_sample(16'sd900, 64'd10, 64'd200000);
        expect_no_trigger();

        // First threshold crossing must trigger and capture exact metadata.
        drive_sample(16'sd1200, 64'd11, 64'd220000);
        if (trigger_pulse !== 1'b1 || trigger_index !== 64'd11 ||
            trigger_timestamp_ns !== 64'd220000 || trigger_value !== 16'sd1200) begin
            $display("FAIL first trigger metadata pulse=%0b index=%0d ts=%0d value=%0d",
                     trigger_pulse, trigger_index, trigger_timestamp_ns, trigger_value);
            $fatal(1);
        end
        if (armed !== 1'b0 || holdoff_remaining !== HOLDOFF) begin
            $display("FAIL first trigger state armed=%0b holdoff=%0d", armed, holdoff_remaining);
            $fatal(1);
        end

        // Staying high must not retrigger because hysteresis has not re-armed.
        drive_sample(16'sd1300, 64'd12, 64'd240000);
        expect_no_trigger();

        // Drop below low threshold re-arms, but holdoff is still active.
        drive_sample(16'sd700, 64'd13, 64'd260000);
        expect_no_trigger();
        if (armed !== 1'b1) begin
            $display("FAIL hysteresis did not re-arm");
            $fatal(1);
        end

        // Crossing high while one holdoff sample remains is suppressed.
        drive_sample(16'sd1250, 64'd14, 64'd280000);
        expect_no_trigger();
        if (holdoff_remaining !== 0) begin
            $display("FAIL holdoff did not expire, remaining=%0d", holdoff_remaining);
            $fatal(1);
        end

        // Once holdoff has expired and the detector is armed, retrigger.
        drive_sample(16'sd1250, 64'd15, 64'd300000);
        if (trigger_pulse !== 1'b1 || trigger_index !== 64'd15 ||
            trigger_timestamp_ns !== 64'd300000 || trigger_value !== 16'sd1250) begin
            $display("FAIL second trigger metadata");
            $fatal(1);
        end

        // Invalid cycles must neither trigger nor consume holdoff samples.
        sample_valid <= 1'b0;
        sample_value <= 16'sd2000;
        repeat (2) @(posedge clk);
        #1;
        expect_no_trigger();
        if (holdoff_remaining !== HOLDOFF) begin
            $display("FAIL invalid cycles consumed holdoff, remaining=%0d", holdoff_remaining);
            $fatal(1);
        end

        if (trigger_count !== 2) begin
            $display("FAIL expected 2 triggers got=%0d", trigger_count);
            $fatal(1);
        end

        $display("PASS RTL-002 triggers=%0d holdoff=%0d", trigger_count, HOLDOFF);
        $finish;
    end
endmodule
