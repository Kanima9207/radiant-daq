`timescale 1ns/1ps

module tb_random_fault_campaign;
    localparam integer TRIALS = 600;

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

    integer trial;
    integer fault_class;
    integer random_bit;
    integer gap_size;
    integer clean_trials = 0;
    integer fault_trials = 0;
    integer detected = 0;
    integer contained = 0;
    integer false_alarms = 0;
    integer class_trials [0:6];
    integer class_detected [0:6];
    integer i;

    reg [31:0] rng = 32'h1ACEB00C;
    reg [31:0] base_sequence;
    reg [255:0] p;
    reg detected_this;
    reg contained_this;

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
        integer j;
        reg [31:0] crc;
        reg feedback;
        begin
            crc = 32'hFFFFFFFF;
            for (j = 223; j >= 0; j = j - 1) begin
                feedback = crc[31] ^ data[j];
                crc = {crc[30:0], 1'b0};
                if (feedback) crc = crc ^ 32'h04C11DB7;
            end
            crc32_msb = crc ^ 32'hFFFFFFFF;
        end
    endfunction

    function [255:0] make_packet;
        input [31:0] seq;
        input [15:0] value;
        reg [223:0] payload;
        begin
            payload = {16'h5244, 8'h01, 8'h01, seq, 8'h02, 8'h00,
                       64'd100, 64'd2000000, value};
            make_packet = {payload, crc32_msb(payload)};
        end
    endfunction

    task advance_rng;
        begin
            rng = {rng[30:0], rng[31] ^ rng[21] ^ rng[1] ^ rng[0]};
            if (rng == 32'd0) rng = 32'h1ACEB00C;
        end
    endtask

    task reset_dut;
        begin
            @(negedge clk);
            rst_n = 1'b0;
            packet_valid = 1'b0;
            clear_safe_request = 1'b0;
            repeat (2) @(posedge clk);
            @(negedge clk);
            rst_n = 1'b1;
            @(posedge clk); #1;
        end
    endtask

    task send_packet;
        input [255:0] pkt;
        begin
            @(negedge clk);
            packet_data = pkt;
            packet_valid = 1'b1;
            while (!packet_ready) @(negedge clk);
            @(posedge clk); #1;
            @(negedge clk);
            packet_valid = 1'b0;
            @(posedge clk); #1;
        end
    endtask

    task score_fault_trial;
        begin
            detected_this = (fault_score != 0) || silence_fault;
            contained_this = diagnostic_request || isolate_link || safe_state;
            fault_trials = fault_trials + 1;
            if (detected_this) detected = detected + 1;
            if (contained_this) contained = contained + 1;
            class_trials[fault_class] = class_trials[fault_class] + 1;
            if (detected_this) class_detected[fault_class] = class_detected[fault_class] + 1;
        end
    endtask

    initial begin
        for (i = 0; i < 7; i = i + 1) begin
            class_trials[i] = 0;
            class_detected[i] = 0;
        end

        for (trial = 0; trial < TRIALS; trial = trial + 1) begin
            advance_rng();
            fault_class = rng % 7;
            advance_rng();
            base_sequence = rng;

            reset_dut();

            case (fault_class)
                0: begin
                    // CLEAN CONTROL: random valid sequence/value, no anomaly.
                    send_packet(make_packet(base_sequence, rng[15:0]));
                    clean_trials = clean_trials + 1;
                    class_trials[0] = class_trials[0] + 1;
                    if (fault_score != 0 || silence_warning || silence_fault ||
                        diagnostic_request || isolate_link || safe_state) begin
                        false_alarms = false_alarms + 1;
                        $fatal(1, "FAIL RTL-013 false alarm trial=%0d", trial);
                    end
                end

                1: begin
                    // CRC corruption: flip one randomized non-header payload bit.
                    advance_rng();
                    random_bit = 32 + (rng % 192);
                    p = make_packet(base_sequence, rng[15:0]);
                    p[random_bit] = ~p[random_bit];
                    send_packet(p);
                    score_fault_trial();
                    if (!detected_this) $fatal(1, "FAIL RTL-013 CRC trial=%0d bit=%0d", trial, random_bit);
                end

                2: begin
                    // Protocol corruption with CRC recomputed, isolating header checks.
                    p = make_packet(base_sequence, rng[15:0]);
                    advance_rng();
                    case (rng % 3)
                        0: p[255:240] = 16'h0000;
                        1: p[239:232] = 8'h7F;
                        default: p[231:224] = 8'h7F;
                    endcase
                    p[31:0] = crc32_msb(p[255:32]);
                    send_packet(p);
                    score_fault_trial();
                    if (!detected_this) $fatal(1, "FAIL RTL-013 protocol trial=%0d", trial);
                end

                3: begin
                    // DROP/GAP: omit 1..4 sequence numbers between valid frames.
                    send_packet(make_packet(base_sequence, rng[15:0]));
                    advance_rng();
                    gap_size = 1 + (rng % 4);
                    send_packet(make_packet(base_sequence + gap_size + 1, rng[15:0]));
                    score_fault_trial();
                    if (!detected_this) $fatal(1, "FAIL RTL-013 drop trial=%0d gap=%0d", trial, gap_size);
                end

                4: begin
                    // DUPLICATE: replay the immediately previous sequence.
                    send_packet(make_packet(base_sequence, rng[15:0]));
                    send_packet(make_packet(base_sequence, rng[15:0]));
                    score_fault_trial();
                    if (!detected_this) $fatal(1, "FAIL RTL-013 duplicate trial=%0d", trial);
                end

                5: begin
                    // REORDER: advance beyond one packet, then deliver the older one.
                    send_packet(make_packet(base_sequence, rng[15:0]));
                    send_packet(make_packet(base_sequence + 2, rng[15:0]));
                    send_packet(make_packet(base_sequence + 1, rng[15:0]));
                    score_fault_trial();
                    if (!detected_this) $fatal(1, "FAIL RTL-013 reorder trial=%0d", trial);
                end

                default: begin
                    // SILENCE: exceed watchdog fault threshold without traffic.
                    repeat (8) @(posedge clk); #1;
                    score_fault_trial();
                    if (!detected_this) $fatal(1, "FAIL RTL-013 silence trial=%0d", trial);
                end
            endcase
        end

        if (fault_trials == 0 || detected != fault_trials || contained != fault_trials)
            $fatal(1, "FAIL RTL-013 totals faults=%0d detected=%0d contained=%0d",
                   fault_trials, detected, contained);
        if (false_alarms != 0)
            $fatal(1, "FAIL RTL-013 false_alarms=%0d", false_alarms);

        // Require every randomized class to have actually been exercised.
        for (i = 0; i < 7; i = i + 1) begin
            if (class_trials[i] == 0)
                $fatal(1, "FAIL RTL-013 class %0d had zero trials", i);
            if (i != 0 && class_detected[i] != class_trials[i])
                $fatal(1, "FAIL RTL-013 class %0d detected=%0d trials=%0d",
                       i, class_detected[i], class_trials[i]);
        end

        $display("RANDOM CAMPAIGN RTL-013 seed=0x1ACEB00C trials=%0d clean=%0d faults=%0d detected=%0d contained=%0d false_alarms=%0d",
                 TRIALS, clean_trials, fault_trials, detected, contained, false_alarms);
        $display("CLASS COUNTS clean=%0d crc=%0d protocol=%0d drop=%0d duplicate=%0d reorder=%0d silence=%0d",
                 class_trials[0], class_trials[1], class_trials[2], class_trials[3],
                 class_trials[4], class_trials[5], class_trials[6]);
        $display("PASS RTL-013 randomized_trials=600 detection_pct=100 containment_pct=100 false_alarms=0");
        $finish;
    end
endmodule
