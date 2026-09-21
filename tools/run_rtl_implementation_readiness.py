import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MAPPING_RUNNER = ROOT / "tools" / "run_rtl_xilinx_mapping.py"
MAPPING_REPORT = ROOT / "build" / "rtl015_xilinx7_resource_report.json"
CONSTRAINT = ROOT / "constraints" / "radiant_daq_100mhz.xdc"

RESULT_DIR = ROOT / "results" / "rtl"
JSON_REPORT = RESULT_DIR / "rtl016_implementation_readiness.json"
TEXT_REPORT = RESULT_DIR / "rtl016_implementation_readiness.txt"

EXPECTED_CLOCK_MHZ = 100.0
EXPECTED_PERIOD_NS = 10.0


def run_mapping():
    result = subprocess.run(
        [sys.executable, str(MAPPING_RUNNER)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.stdout:
        print(result.stdout, end="")

    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")

    return result.returncode == 0


def check_constraint():
    if not CONSTRAINT.is_file():
        return False, "constraint file missing"

    text = CONSTRAINT.read_text(encoding="utf-8")

    required = [
        "create_clock",
        "-period 10.000",
        "[get_ports clk]",
    ]

    missing = [item for item in required if item not in text]

    if missing:
        return False, "missing expected clock declaration"

    return True, "100 MHz / 10.000 ns clock intent declared"


def main():
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print("RADIANT-DAQ RTL-016 IMPLEMENTATION READINESS")
    print("=" * 64)

    mapping_runner_pass = run_mapping()

    if not MAPPING_REPORT.is_file():
        print("\nRTL-016 FAIL: RTL-015 mapping report was not generated.")
        return 1

    mapping = json.loads(MAPPING_REPORT.read_text(encoding="utf-8"))

    mapping_pass = (
        mapping_runner_pass
        and mapping.get("status") == "mapped"
        and mapping.get("target_family") == "xilinx_7series"
    )

    constraint_pass, constraint_note = check_constraint()

    clock_pass = (
        mapping.get("clock_target_mhz") == EXPECTED_CLOCK_MHZ
        and mapping.get("clock_period_ns") == EXPECTED_PERIOD_NS
    )

    readiness_pass = mapping_pass and constraint_pass and clock_pass

    report = {
        "milestone": "RTL-016",
        "name": "FPGA implementation readiness",
        "status": "pass" if readiness_pass else "fail",
        "top": mapping.get("top"),
        "target_family": mapping.get("target_family"),
        "clock_target_mhz": mapping.get("clock_target_mhz"),
        "clock_period_ns": mapping.get("clock_period_ns"),
        "mapped_cell_count": mapping.get("mapped_cell_count"),
        "estimated_luts": mapping.get("estimated_luts"),
        "estimated_flip_flops": mapping.get("estimated_flip_flops"),
        "carry4": mapping.get("carry4"),
        "muxf": mapping.get("muxf"),
        "checks": {
            "xilinx7_logical_mapping": mapping_pass,
            "clock_constraint": constraint_pass,
            "clock_metadata_consistent": clock_pass,
        },
        "constraint_note": constraint_note,
        "physical_place_and_route": "not performed",
        "static_timing_analysis": "not performed",
        "timing_closure": "not claimed",
        "physical_fpga_validation": "not performed",
        "scope": (
            "Implementation-readiness benchmark based on reproducible "
            "Xilinx 7-series logical mapping and explicit timing intent. "
            "This result does not constitute placement/routing or "
            "post-route timing closure."
        ),
    }

    JSON_REPORT.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "RADIANT-DAQ RTL-016 IMPLEMENTATION READINESS",
        "=" * 52,
        "",
        f"Status                 : {'PASS' if readiness_pass else 'FAIL'}",
        f"Top                    : {mapping.get('top')}",
        f"Target family          : {mapping.get('target_family')}",
        f"Clock target           : {mapping.get('clock_target_mhz')} MHz",
        f"Clock period           : {mapping.get('clock_period_ns'):.3f} ns",
        "",
        "Xilinx-7 logical mapping",
        "-" * 52,
        f"Mapped cells           : {mapping.get('mapped_cell_count')}",
        f"Estimated LUTs         : {mapping.get('estimated_luts')}",
        f"Estimated flip-flops   : {mapping.get('estimated_flip_flops')}",
        f"CARRY4                 : {mapping.get('carry4')}",
        f"MUXF                    : {mapping.get('muxf')}",
        "",
        "Readiness checks",
        "-" * 52,
        f"Logical mapping        : {'PASS' if mapping_pass else 'FAIL'}",
        f"100 MHz constraint     : {'PASS' if constraint_pass else 'FAIL'}",
        f"Clock consistency      : {'PASS' if clock_pass else 'FAIL'}",
        "",
        "Validation boundary",
        "-" * 52,
        "Physical P&R           : NOT PERFORMED",
        "Static timing          : NOT PERFORMED",
        "Timing closure         : NOT CLAIMED",
        "Physical FPGA test     : NOT PERFORMED",
        "",
        "Conclusion",
        "-" * 52,
        (
            "PASS - RTL is reproducibly mapped to Xilinx 7-series "
            "primitives with a declared 100 MHz implementation target."
            if readiness_pass
            else "FAIL - one or more implementation-readiness checks failed."
        ),
        "",
    ]

    TEXT_REPORT.write_text("\n".join(lines), encoding="utf-8")

    print()
    print(f"Logical mapping       : {'PASS' if mapping_pass else 'FAIL'}")
    print(f"100 MHz constraint    : {'PASS' if constraint_pass else 'FAIL'}")
    print(f"Clock consistency     : {'PASS' if clock_pass else 'FAIL'}")
    print()
    print(f"Mapped cells          : {mapping.get('mapped_cell_count')}")
    print(f"Estimated LUTs        : {mapping.get('estimated_luts')}")
    print(f"Estimated FFs         : {mapping.get('estimated_flip_flops')}")
    print(f"CARRY4                : {mapping.get('carry4')}")
    print(f"MUXF                   : {mapping.get('muxf')}")
    print()
    print("Physical P&R          : NOT PERFORMED")
    print("Timing closure        : NOT CLAIMED")
    print()
    print(
        "RTL-016 RESULT        : "
        + ("PASS" if readiness_pass else "FAIL")
    )
    print(f"JSON report           : {JSON_REPORT.relative_to(ROOT)}")
    print(f"Text report           : {TEXT_REPORT.relative_to(ROOT)}")

    return 0 if readiness_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())