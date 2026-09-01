`timescale 1ns/1ps

module tb_acquisition_timebase;
    parameter integer SAMPLE_RATE_HZ = 50_000;
    localparam integer FRAME_SAMPLES = 4;

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg sample_valid = 1'b0;
    reg frame_end = 1'b0;
    wire [63:0] sample_index;
    wire [63:0] timestamp_ns;
    wire [31:0] packet_sequence;

    integer accepted;
    integer expected_sequence;
    reg [63:0] expected_timestamp;

    acquisition_timebase #(
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_valid(sample_valid),
        .frame_end(frame_end),
        .sample_index(sample_index),
        .timestamp_ns(timestamp_ns),
        .packet_sequence(packet_sequence)
    );

    always #5 clk = ~clk;

    task check_outputs;
        begin
            expected_timestamp = (accepted * 64'd1000000000) / SAMPLE_RATE_HZ;
            expected_sequence = accepted / FRAME_SAMPLES;
            if (sample_index !== accepted) begin
                $display("FAIL sample_index expected=%0d got=%0d", accepted, sample_index);
                $fatal(1);
            end
            if (timestamp_ns !== expected_timestamp) begin
                $display("FAIL timestamp expected=%0d got=%0d", expected_timestamp, timestamp_ns);
                $fatal(1);
            end
            if (packet_sequence !== expected_sequence) begin
                $display("FAIL packet_sequence expected=%0d got=%0d", expected_sequence, packet_sequence);
                $fatal(1);
            end
        end
    endtask

    initial begin
        accepted = 0;
        repeat (2) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        #1;
        check_outputs();

        // Verify stalled cycles do not advance state.
        repeat (3) begin
            sample_valid <= 1'b0;
            frame_end <= 1'b0;
            @(posedge clk);
            #1;
            check_outputs();
        end

        // Accept 20 samples, ending a frame every four samples.
        repeat (20) begin
            sample_valid <= 1'b1;
            frame_end <= ((accepted % FRAME_SAMPLES) == FRAME_SAMPLES - 1);
            @(posedge clk);
            accepted = accepted + 1;
            #1;
            check_outputs();
        end

        sample_valid <= 1'b0;
        frame_end <= 1'b0;
        @(posedge clk);
        #1;
        check_outputs();

        $display("PASS RTL-001 SAMPLE_RATE_HZ=%0d samples=%0d", SAMPLE_RATE_HZ, accepted);
        $finish;
    end
endmodule
