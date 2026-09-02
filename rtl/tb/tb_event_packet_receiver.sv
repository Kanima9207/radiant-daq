`timescale 1ns/1ps

module tb_event_packet_receiver;
    reg clk = 1'b0;
    reg rst_n = 1'b0;

    reg event_valid_in = 1'b0;
    wire event_ready_in;
    reg [7:0] event_channel_in = 8'd0;
    reg [63:0] event_index_in = 64'd0;
    reg [63:0] event_timestamp_in = 64'd0;
    reg signed [15:0] event_value_in = 16'sd0;

    wire tx_packet_valid;
    wire tx_packet_ready;
    wire [255:0] tx_packet_data;
    wire [31:0] tx_packet_sequence;

    reg [255:0] corrupt_mask = 256'd0;
    wire [255:0] rx_packet_data = tx_packet_data ^ corrupt_mask;

    wire rx_event_valid;
    reg rx_event_ready = 1'b0;
    wire [31:0] rx_event_sequence;
    wire [7:0] rx_event_channel;
    wire [63:0] rx_event_index;
    wire [63:0] rx_event_timestamp_ns;
    wire signed [15:0] rx_event_value;
    wire crc_error_pulse;
    wire protocol_error_pulse;
    wire [31:0] accepted_packets;
    wire [31:0] rejected_packets;
    wire [31:0] crc_error_count;
    wire [31:0] protocol_error_count;

    reg [255:0] held_packet;

    event_packetizer tx_i (
        .clk(clk),
        .rst_n(rst_n),
        .event_valid(event_valid_in),
        .event_ready(event_ready_in),
        .event_channel(event_channel_in),
        .event_index(event_index_in),
        .event_timestamp_ns(event_timestamp_in),
        .event_value(event_value_in),
        .packet_valid(tx_packet_valid),
        .packet_ready(tx_packet_ready),
        .packet_data(tx_packet_data),
        .packet_sequence(tx_packet_sequence)
    );

    event_packet_receiver rx_i (
        .clk(clk),
        .rst_n(rst_n),
        .packet_valid(tx_packet_valid),
        .packet_ready(tx_packet_ready),
        .packet_data(rx_packet_data),
        .event_valid(rx_event_valid),
        .event_ready(rx_event_ready),
        .event_sequence(rx_event_sequence),
        .event_channel(rx_event_channel),
        .event_index(rx_event_index),
        .event_timestamp_ns(rx_event_timestamp_ns),
        .event_value(rx_event_value),
        .crc_error_pulse(crc_error_pulse),
        .protocol_error_pulse(protocol_error_pulse),
        .accepted_packets(accepted_packets),
        .rejected_packets(rejected_packets),
        .crc_error_count(crc_error_count),
        .protocol_error_count(protocol_error_count)
    );

    always #5 clk = ~clk;

    task load_event;
        input [7:0] ch;
        input [63:0] idx;
        input [63:0] ts;
        input signed [15:0] val;
        begin
            event_channel_in = ch;
            event_index_in = idx;
            event_timestamp_in = ts;
            event_value_in = val;
            event_valid_in = 1'b1;
        end
    endtask

    task release_event;
        begin
            event_valid_in = 1'b0;
        end
    endtask

    initial begin
        repeat (2) @(posedge clk);
        rst_n <= 1'b1;
        @(posedge clk);
        #1;

        // Packet 0: clean frame held under receiver backpressure.
        load_event(8'd2, 64'd100, 64'd2_000_000, -16'sd321);
        rx_event_ready = 1'b0;
        corrupt_mask = 256'd0;
        #1;

        if (!tx_packet_valid || !rx_event_valid || tx_packet_ready || event_ready_in) begin
            $display("FAIL clean packet did not honor backpressure");
            $fatal(1);
        end
        if (rx_event_sequence !== 32'd0 || rx_event_channel !== 8'd2 ||
            rx_event_index !== 64'd100 || rx_event_timestamp_ns !== 64'd2_000_000 ||
            rx_event_value !== -16'sd321) begin
            $display("FAIL clean packet decode mismatch");
            $fatal(1);
        end

        held_packet = tx_packet_data;
        repeat (3) begin
            @(posedge clk);
            #1;
            if (tx_packet_data !== held_packet || tx_packet_sequence !== 32'd0) begin
                $display("FAIL packet changed under backpressure");
                $fatal(1);
            end
        end

        rx_event_ready = 1'b1;
        @(posedge clk);
        #1;
        release_event();
        if (accepted_packets !== 32'd1 || rejected_packets !== 32'd0 ||
            tx_packet_sequence !== 32'd1) begin
            $display("FAIL clean packet accounting accepted=%0d rejected=%0d seq=%0d",
                     accepted_packets, rejected_packets, tx_packet_sequence);
            $fatal(1);
        end

        // Packet 1: flip one timestamp payload bit. Header remains valid, CRC fails.
        load_event(8'd3, 64'd101, 64'd2_020_000, 16'sd777);
        corrupt_mask = (256'd1 << 80);
        #1;
        if (rx_event_valid !== 1'b0 || tx_packet_ready !== 1'b1) begin
            $display("FAIL corrupted packet was not immediately rejectable");
            $fatal(1);
        end
        @(posedge clk);
        #1;
        release_event();
        corrupt_mask = 256'd0;
        if (!crc_error_pulse || protocol_error_pulse ||
            accepted_packets !== 32'd1 || rejected_packets !== 32'd1 ||
            crc_error_count !== 32'd1 || protocol_error_count !== 32'd0 ||
            tx_packet_sequence !== 32'd2) begin
            $display("FAIL CRC-only rejection accounting");
            $fatal(1);
        end

        // Let one cycle clear error pulses.
        @(posedge clk);
        #1;

        // Packet 2: corrupt the magic header. This must flag a protocol error.
        load_event(8'd1, 64'd102, 64'd2_040_000, 16'sd888);
        corrupt_mask = (256'd1 << 255);
        #1;
        if (rx_event_valid !== 1'b0 || tx_packet_ready !== 1'b1) begin
            $display("FAIL bad-header packet was not rejected");
            $fatal(1);
        end
        @(posedge clk);
        #1;
        release_event();
        corrupt_mask = 256'd0;
        if (!protocol_error_pulse || accepted_packets !== 32'd1 ||
            rejected_packets !== 32'd2 || protocol_error_count !== 32'd1 ||
            tx_packet_sequence !== 32'd3) begin
            $display("FAIL protocol rejection accounting");
            $fatal(1);
        end

        @(posedge clk);
        #1;

        // Packet 3: clean packet proves recovery after two rejected frames.
        load_event(8'd0, 64'd103, 64'd2_060_000, 16'sd999);
        corrupt_mask = 256'd0;
        rx_event_ready = 1'b1;
        #1;
        if (!rx_event_valid || rx_event_sequence !== 32'd3 ||
            rx_event_channel !== 8'd0 || rx_event_index !== 64'd103 ||
            rx_event_timestamp_ns !== 64'd2_060_000 || rx_event_value !== 16'sd999) begin
            $display("FAIL clean recovery packet decode");
            $fatal(1);
        end
        @(posedge clk);
        #1;
        release_event();

        if (accepted_packets !== 32'd2 || rejected_packets !== 32'd2 ||
            crc_error_count !== 32'd2 || protocol_error_count !== 32'd1 ||
            tx_packet_sequence !== 32'd4) begin
            $display("FAIL final accounting accepted=%0d rejected=%0d crc=%0d proto=%0d seq=%0d",
                     accepted_packets, rejected_packets, crc_error_count,
                     protocol_error_count, tx_packet_sequence);
            $fatal(1);
        end

        $display("PASS RTL-007 accepted=2 rejected=2 crc_errors=2 protocol_errors=1 recovery_seq=3");
        $finish;
    end
endmodule
