// RADIANT-DAQ RTL-009: watchdog + link health state machine.
//
// Combines transport silence and integrity/sequence fault pulses into a compact
// synthesizable health model. A saturating fault score accumulates anomalies;
// accepted in-order traffic heals the score one point at a time. An independent
// silence watchdog escalates if no packet (good or rejected) is consumed.
//
// Health encoding:
//   2'b00 HEALTHY
//   2'b01 WARNING
//   2'b10 DEGRADED
//   2'b11 FAULT
//
// Verification is simulation-only; thresholds are configurable and are not a
// claim of physical-link reliability.

module link_health_monitor #(
    parameter integer SILENCE_WARN_CYCLES  = 8,
    parameter integer SILENCE_FAULT_CYCLES = 16,
    parameter integer WARNING_SCORE        = 1,
    parameter integer DEGRADED_SCORE       = 3,
    parameter integer FAULT_SCORE          = 5,
    parameter integer SCORE_WIDTH          = 8,
    parameter integer SILENCE_WIDTH        = 32
) (
    input  wire                         clk,
    input  wire                         rst_n,

    input  wire                         packet_activity_pulse,
    input  wire                         good_event_pulse,
    input  wire                         crc_error_pulse,
    input  wire                         protocol_error_pulse,
    input  wire                         gap_pulse,
    input  wire                         duplicate_pulse,
    input  wire                         out_of_order_pulse,

    output reg  [SCORE_WIDTH-1:0]       fault_score,
    output reg  [SILENCE_WIDTH-1:0]     silence_cycles,
    output reg                          silence_warning,
    output reg                          silence_fault,
    output reg  [1:0]                   health_state
);

    localparam [1:0] HEALTHY  = 2'b00;
    localparam [1:0] WARNING  = 2'b01;
    localparam [1:0] DEGRADED = 2'b10;
    localparam [1:0] FAULT    = 2'b11;

    localparam [SCORE_WIDTH-1:0] SCORE_MAX = {SCORE_WIDTH{1'b1}};

    reg [SCORE_WIDTH:0] added_score;
    reg [SCORE_WIDTH:0] score_candidate;

    always @* begin
        added_score = {(SCORE_WIDTH+1){1'b0}};
        if (crc_error_pulse)
            added_score = added_score + 1;
        if (protocol_error_pulse)
            added_score = added_score + 2;
        if (gap_pulse)
            added_score = added_score + 2;
        if (duplicate_pulse)
            added_score = added_score + 1;
        if (out_of_order_pulse)
            added_score = added_score + 2;

        score_candidate = {1'b0, fault_score} + added_score;
        if (added_score == 0 && good_event_pulse && fault_score != 0)
            score_candidate = {1'b0, fault_score} - 1'b1;
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            fault_score <= {SCORE_WIDTH{1'b0}};
            silence_cycles <= {SILENCE_WIDTH{1'b0}};
        end else begin
            if (score_candidate[SCORE_WIDTH])
                fault_score <= SCORE_MAX;
            else
                fault_score <= score_candidate[SCORE_WIDTH-1:0];

            if (packet_activity_pulse)
                silence_cycles <= {SILENCE_WIDTH{1'b0}};
            else if (silence_cycles != {SILENCE_WIDTH{1'b1}})
                silence_cycles <= silence_cycles + 1'b1;
        end
    end

    always @* begin
        silence_warning = (silence_cycles >= SILENCE_WARN_CYCLES);
        silence_fault = (silence_cycles >= SILENCE_FAULT_CYCLES);

        if (silence_fault || fault_score >= FAULT_SCORE)
            health_state = FAULT;
        else if (fault_score >= DEGRADED_SCORE)
            health_state = DEGRADED;
        else if (silence_warning || fault_score >= WARNING_SCORE)
            health_state = WARNING;
        else
            health_state = HEALTHY;
    end

`ifndef SYNTHESIS
    initial begin
        if (SILENCE_WARN_CYCLES <= 0 || SILENCE_FAULT_CYCLES <= SILENCE_WARN_CYCLES)
            $error("silence thresholds must satisfy 0 < WARN < FAULT");
        if (!(WARNING_SCORE < DEGRADED_SCORE && DEGRADED_SCORE < FAULT_SCORE))
            $error("score thresholds must satisfy WARNING < DEGRADED < FAULT");
    end
`endif

endmodule
