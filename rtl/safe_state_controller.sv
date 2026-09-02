// RADIANT-DAQ RTL-010: automatic recovery / safe-state controller.
//
// Converts RTL-009 link-health states into explicit containment and recovery
// actions. WARNING requests diagnostics, DEGRADED isolates the link and issues
// a bounded recovery pulse, and FAULT enters a latched safe state. A safe-state
// exit requires an explicit clear request plus sustained HEALTHY status.
//
// This is a synthesizable control policy verified only in simulation. It does
// not represent a physical interlock or certified safety function.

module safe_state_controller #(
    parameter integer RECOVERY_PULSE_CYCLES = 2,
    parameter integer HEALTHY_CLEAR_CYCLES  = 3,
    parameter integer COUNTER_WIDTH         = 16
) (
    input  wire                     clk,
    input  wire                     rst_n,
    input  wire [1:0]               health_state,
    input  wire                     clear_safe_request,

    output reg                      diagnostic_request,
    output reg                      isolate_link,
    output reg                      recovery_request,
    output reg                      safe_state,
    output reg                      acquisition_enable,
    output reg  [31:0]              recovery_count,
    output reg  [31:0]              safe_entry_count
);

    localparam [1:0] HEALTHY  = 2'b00;
    localparam [1:0] WARNING  = 2'b01;
    localparam [1:0] DEGRADED = 2'b10;
    localparam [1:0] FAULT    = 2'b11;

    reg [COUNTER_WIDTH-1:0] recovery_remaining;
    reg [COUNTER_WIDTH-1:0] healthy_streak;
    reg degraded_seen;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            recovery_remaining <= {COUNTER_WIDTH{1'b0}};
            healthy_streak <= {COUNTER_WIDTH{1'b0}};
            degraded_seen <= 1'b0;
            safe_state <= 1'b0;
            recovery_count <= 32'd0;
            safe_entry_count <= 32'd0;
        end else begin
            // Track sustained healthy operation for deliberate safe-state exit.
            if (health_state == HEALTHY) begin
                if (healthy_streak < HEALTHY_CLEAR_CYCLES)
                    healthy_streak <= healthy_streak + 1'b1;
            end else begin
                healthy_streak <= {COUNTER_WIDTH{1'b0}};
            end

            // One bounded recovery attempt per DEGRADED episode.
            if (health_state != DEGRADED)
                degraded_seen <= 1'b0;
            else if (!degraded_seen && !safe_state) begin
                degraded_seen <= 1'b1;
                recovery_remaining <= RECOVERY_PULSE_CYCLES;
                recovery_count <= recovery_count + 1'b1;
            end

            if (recovery_remaining != 0)
                recovery_remaining <= recovery_remaining - 1'b1;

            // FAULT containment is latched. It cannot clear merely because the
            // health score later decays; explicit authorization is required.
            if (health_state == FAULT && !safe_state) begin
                safe_state <= 1'b1;
                safe_entry_count <= safe_entry_count + 1'b1;
                recovery_remaining <= {COUNTER_WIDTH{1'b0}};
            end else if (safe_state && clear_safe_request &&
                         health_state == HEALTHY &&
                         healthy_streak >= HEALTHY_CLEAR_CYCLES) begin
                safe_state <= 1'b0;
            end
        end
    end

    always @* begin
        diagnostic_request = (health_state == WARNING) ||
                             (health_state == DEGRADED) || safe_state;
        recovery_request = (recovery_remaining != 0) && !safe_state;
        isolate_link = safe_state || (health_state == DEGRADED) ||
                       (health_state == FAULT);
        acquisition_enable = !safe_state;
    end

`ifndef SYNTHESIS
    initial begin
        if (RECOVERY_PULSE_CYCLES <= 0)
            $error("RECOVERY_PULSE_CYCLES must be > 0");
        if (HEALTHY_CLEAR_CYCLES <= 0)
            $error("HEALTHY_CLEAR_CYCLES must be > 0");
    end
`endif

endmodule
