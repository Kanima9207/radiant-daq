// RADIANT-DAQ RTL-011: integrated fault-tolerant DAQ node.
//
// End-to-end composition:
// acquisition/timebase -> multi-channel triggers -> event FIFO -> packetizer ->
// loopback transport fault boundary -> CRC/protocol receiver -> sequence monitor
// -> link health -> automatic recovery/safe-state controller.
//
// transport_drop and transport_xor_mask are verification/fault-injection hooks.
// A dropped packet is consumed from the transmitter but withheld from the
// receiver. XOR corruption is applied only at the transport boundary.
//
// This module is synthesizable apart from the intended verification use of the
// fault-injection inputs. Verification is simulation-only; no physical FPGA,
// link, timing-closure, or safety-certification claim is made.

module fault_tolerant_daq_node #(
    parameter integer CHANNELS          = 4,
    parameter integer SAMPLE_RATE_HZ    = 50_000,
    parameter integer SAMPLE_WIDTH      = 16,
    parameter integer INDEX_WIDTH       = 64,
    parameter integer TIME_WIDTH        = 64,
    parameter integer SEQ_WIDTH         = 32,
    parameter integer HOLDOFF_WIDTH     = 32,
    parameter integer FIFO_DEPTH        = 4,
    parameter integer CHANNEL_ID_WIDTH  = (CHANNELS <= 1) ? 1 : $clog2(CHANNELS),
    parameter integer FIFO_COUNT_WIDTH  = $clog2(FIFO_DEPTH + 1),
    parameter integer SILENCE_WARN_CYCLES  = 64,
    parameter integer SILENCE_FAULT_CYCLES = 128,
    parameter integer WARNING_SCORE        = 1,
    parameter integer DEGRADED_SCORE       = 3,
    parameter integer FAULT_SCORE          = 5,
    parameter integer RECOVERY_PULSE_CYCLES = 2,
    parameter integer HEALTHY_CLEAR_CYCLES  = 3
) (
    input  wire                                      clk,
    input  wire                                      rst_n,
    input  wire                                      sample_valid,
    input  wire                                      frame_end,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  sample_values,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  threshold_high,
    input  wire signed [CHANNELS*SAMPLE_WIDTH-1:0]  threshold_low,
    input  wire        [CHANNELS*HOLDOFF_WIDTH-1:0] holdoff_samples,

    input  wire                                      transport_drop,
    input  wire [255:0]                              transport_xor_mask,
    input  wire                                      clear_safe_request,

    output wire                                      received_event_valid,
    output wire [31:0]                               received_event_sequence,
    output wire [7:0]                                received_event_channel,
    output wire [63:0]                               received_event_index,
    output wire [63:0]                               received_event_timestamp_ns,
    output wire signed [15:0]                       received_event_value,

    output wire [1:0]                                health_state,
    output wire [7:0]                                fault_score,
    output wire                                      diagnostic_request,
    output wire                                      isolate_link,
    output wire                                      recovery_request,
    output wire                                      safe_state,
    output wire                                      acquisition_enable,
    output wire [31:0]                               recovery_count,
    output wire [31:0]                               safe_entry_count,

    output wire                                      crc_error_pulse,
    output wire                                      protocol_error_pulse,
    output wire                                      gap_pulse,
    output wire                                      duplicate_pulse,
    output wire                                      out_of_order_pulse,

    output wire [INDEX_WIDTH-1:0]                   next_sample_index,
    output wire [TIME_WIDTH-1:0]                    next_timestamp_ns,
    output wire [SEQ_WIDTH-1:0]                     acquisition_packet_sequence,
    output wire [31:0]                               transmit_event_sequence,
    output wire [FIFO_COUNT_WIDTH-1:0]              fifo_occupancy,
    output wire                                      producer_overflow,
    output wire                                      fifo_overflow
);

    wire gated_sample_valid = sample_valid && acquisition_enable;

    wire tx_packet_valid;
    wire tx_packet_ready;
    wire [255:0] tx_packet_data;
    wire [CHANNELS-1:0] pending_events;

    wire rx_packet_valid;
    wire rx_packet_ready;
    wire [255:0] rx_packet_data;

    wire [31:0] silence_cycles;
    wire silence_warning;
    wire silence_fault;

    packetized_multi_channel_pipeline #(
        .CHANNELS(CHANNELS),
        .SAMPLE_RATE_HZ(SAMPLE_RATE_HZ),
        .SAMPLE_WIDTH(SAMPLE_WIDTH),
        .INDEX_WIDTH(INDEX_WIDTH),
        .TIME_WIDTH(TIME_WIDTH),
        .SEQ_WIDTH(SEQ_WIDTH),
        .HOLDOFF_WIDTH(HOLDOFF_WIDTH),
        .FIFO_DEPTH(FIFO_DEPTH),
        .CHANNEL_ID_WIDTH(CHANNEL_ID_WIDTH),
        .FIFO_COUNT_WIDTH(FIFO_COUNT_WIDTH)
    ) transmit_i (
        .clk(clk), .rst_n(rst_n),
        .sample_valid(gated_sample_valid), .frame_end(frame_end),
        .sample_values(sample_values), .threshold_high(threshold_high),
        .threshold_low(threshold_low), .holdoff_samples(holdoff_samples),
        .packet_ready(tx_packet_ready), .packet_valid(tx_packet_valid),
        .packet_data(tx_packet_data), .event_packet_sequence(transmit_event_sequence),
        .next_sample_index(next_sample_index), .next_timestamp_ns(next_timestamp_ns),
        .acquisition_packet_sequence(acquisition_packet_sequence),
        .pending_events(pending_events), .fifo_occupancy(fifo_occupancy),
        .producer_overflow(producer_overflow), .fifo_overflow(fifo_overflow)
    );

    // Verification transport boundary. Dropping still acknowledges the source,
    // modelling a packet lost after successful transmission.
    assign tx_packet_ready = transport_drop ? 1'b1 : rx_packet_ready;
    assign rx_packet_valid = tx_packet_valid && !transport_drop;
    assign rx_packet_data = tx_packet_data ^ transport_xor_mask;

    health_monitored_event_packet_receiver #(
        .SILENCE_WARN_CYCLES(SILENCE_WARN_CYCLES),
        .SILENCE_FAULT_CYCLES(SILENCE_FAULT_CYCLES),
        .WARNING_SCORE(WARNING_SCORE),
        .DEGRADED_SCORE(DEGRADED_SCORE),
        .FAULT_SCORE(FAULT_SCORE)
    ) receive_i (
        .clk(clk), .rst_n(rst_n),
        .packet_valid(rx_packet_valid), .packet_ready(rx_packet_ready),
        .packet_data(rx_packet_data),
        .event_valid(received_event_valid), .event_ready(1'b1),
        .event_sequence(received_event_sequence),
        .event_channel(received_event_channel), .event_index(received_event_index),
        .event_timestamp_ns(received_event_timestamp_ns),
        .event_value(received_event_value),
        .crc_error_pulse(crc_error_pulse),
        .protocol_error_pulse(protocol_error_pulse),
        .gap_pulse(gap_pulse), .duplicate_pulse(duplicate_pulse),
        .out_of_order_pulse(out_of_order_pulse),
        .fault_score(fault_score), .silence_cycles(silence_cycles),
        .silence_warning(silence_warning), .silence_fault(silence_fault),
        .health_state(health_state)
    );

    safe_state_controller #(
        .RECOVERY_PULSE_CYCLES(RECOVERY_PULSE_CYCLES),
        .HEALTHY_CLEAR_CYCLES(HEALTHY_CLEAR_CYCLES)
    ) safety_i (
        .clk(clk), .rst_n(rst_n), .health_state(health_state),
        .clear_safe_request(clear_safe_request),
        .diagnostic_request(diagnostic_request), .isolate_link(isolate_link),
        .recovery_request(recovery_request), .safe_state(safe_state),
        .acquisition_enable(acquisition_enable),
        .recovery_count(recovery_count), .safe_entry_count(safe_entry_count)
    );

endmodule
