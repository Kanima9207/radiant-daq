import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
YOSYS_SCRIPT = ROOT / "rtl" / "yosys_rtl016_xc7a35t.ys"
XDC = ROOT / "constraints" / "radiant_daq_xc7a35t_100mhz.xdc"
SYNTH_JSON = BUILD / "rtl016_xc7a35t.json"
ROUTED_JSON = BUILD / "rtl016_xc7a35t_routed.json"
FASM = BUILD / "rtl016_xc7a35t.fasm"
REPORT = BUILD / "rtl016_timing_report.json"
TOP = "radiant_daq_impl_top"
TARGET = "XC7A35T-CSG324"
CLOCK_MHZ = 100.0
CLOCK_PERIOD_NS = 10.0


def _find_executable(name: str):
    candidate = shutil.which(name)
    if candidate:
        return candidate, None

    msys2_bin = Path(r"C:\msys64\ucrt64\bin")
    exe = msys2_bin / f"{name}.exe"
    if exe.is_file():
        return str(exe), msys2_bin
    return None, None


def _find_chipdb():
    for env_name in ("RADIANT_XC7A35T_CHIPDB", "NEXTPNR_XILINX_CHIPDB"):
        value = os.environ.get(env_name)
        if value:
            path = Path(value).expanduser()
            if path.is_file():
                return path, env_name
    return None, None


def _write_report(report):
    BUILD.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _child_env(extra_bin):
    env = os.environ.copy()
    if extra_bin is not None:
        env["PATH"] = str(extra_bin) + os.pathsep + env.get("PATH", "")
    return env


def _parse_fmax(text: str):
    matches = re.findall(
        r"Max frequency for clock[^:]*:\s*([0-9]+(?:\.[0-9]+)?)\s*MHz",
        text,
        flags=re.IGNORECASE,
    )
    if not matches:
        matches = re.findall(
            r"Max frequency[^\n]*?([0-9]+(?:\.[0-9]+)?)\s*MHz",
            text,
            flags=re.IGNORECASE,
        )
    if not matches:
        return None
    return min(float(value) for value in matches)


def main():
    BUILD.mkdir(exist_ok=True)

    yosys, yosys_bin = _find_executable("yosys")
    if not yosys:
        report = {
            "status": "unavailable",
            "stage": "synthesis",
            "tool": "yosys",
            "top": TOP,
            "target": TARGET,
            "clock_target_mhz": CLOCK_MHZ,
            "note": "Yosys not found; RTL-016 implementation could not start.",
        }
        _write_report(report)
        print("RTL-016 unavailable: Yosys not found")
        return 0

    synth = subprocess.run(
        [yosys, "-s", str(YOSYS_SCRIPT)],
        cwd=ROOT,
        env=_child_env(yosys_bin),
        capture_output=True,
        text=True,
        check=False,
    )
    if synth.returncode != 0:
        sys.stdout.write(synth.stdout)
        sys.stderr.write(synth.stderr)
        return synth.returncode

    nextpnr, nextpnr_bin = _find_executable("nextpnr-xilinx")
    if not nextpnr:
        report = {
            "status": "synthesized_unrouted",
            "stage": "place_and_route",
            "tool": "nextpnr-xilinx",
            "top": TOP,
            "target": TARGET,
            "clock_target_mhz": CLOCK_MHZ,
            "clock_period_ns": CLOCK_PERIOD_NS,
            "synth_netlist": str(SYNTH_JSON.relative_to(ROOT)),
            "note": "Synthesis completed, but nextpnr-xilinx was not found; no routed timing result was produced.",
        }
        _write_report(report)
        print("RTL-016 SYNTHESIS PASS / P&R UNAVAILABLE")
        print("Reason             : nextpnr-xilinx not found")
        print(f"Report             : {REPORT.relative_to(ROOT)}")
        return 0

    chipdb, chipdb_source = _find_chipdb()
    if chipdb is None:
        report = {
            "status": "synthesized_unrouted",
            "stage": "place_and_route",
            "tool": "nextpnr-xilinx",
            "top": TOP,
            "target": TARGET,
            "clock_target_mhz": CLOCK_MHZ,
            "clock_period_ns": CLOCK_PERIOD_NS,
            "synth_netlist": str(SYNTH_JSON.relative_to(ROOT)),
            "note": "nextpnr-xilinx was found, but no XC7A35T chip database was configured. Set RADIANT_XC7A35T_CHIPDB to the chipdb file path.",
        }
        _write_report(report)
        print("RTL-016 SYNTHESIS PASS / P&R UNAVAILABLE")
        print("Reason             : XC7A35T nextpnr chipdb not configured")
        print("Set                : RADIANT_XC7A35T_CHIPDB=<path-to-chipdb>")
        print(f"Report             : {REPORT.relative_to(ROOT)}")
        return 0

    env = _child_env(nextpnr_bin)
    command = [
        nextpnr,
        "--chipdb", str(chipdb),
        "--json", str(SYNTH_JSON),
        "--xdc", str(XDC),
        "--write", str(ROUTED_JSON),
        "--fasm", str(FASM),
        "--freq", f"{CLOCK_MHZ:g}",
        "--timing-allow-fail",
    ]
    route = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    route_text = route.stdout + "\n" + route.stderr
    if route.returncode != 0:
        report = {
            "status": "place_route_error",
            "stage": "place_and_route",
            "tool": "nextpnr-xilinx",
            "top": TOP,
            "target": TARGET,
            "clock_target_mhz": CLOCK_MHZ,
            "clock_period_ns": CLOCK_PERIOD_NS,
            "chipdb": str(chipdb),
            "returncode": route.returncode,
            "note": "nextpnr-xilinx returned an error; no timing-closure claim is valid.",
        }
        _write_report(report)
        sys.stdout.write(route.stdout)
        sys.stderr.write(route.stderr)
        return route.returncode

    fmax_mhz = _parse_fmax(route_text)
    critical_path_ns = None if not fmax_mhz else 1000.0 / fmax_mhz
    slack_ns = None if critical_path_ns is None else CLOCK_PERIOD_NS - critical_path_ns
    timing_met = None if fmax_mhz is None else fmax_mhz >= CLOCK_MHZ

    report = {
        "status": "routed",
        "tool": "nextpnr-xilinx",
        "top": TOP,
        "target": TARGET,
        "clock_target_mhz": CLOCK_MHZ,
        "clock_period_ns": CLOCK_PERIOD_NS,
        "fmax_mhz": fmax_mhz,
        "critical_path_estimate_ns": critical_path_ns,
        "derived_slack_ns": slack_ns,
        "timing_met": timing_met,
        "chipdb": str(chipdb),
        "chipdb_source": chipdb_source,
        "synth_netlist": str(SYNTH_JSON.relative_to(ROOT)),
        "routed_netlist": str(ROUTED_JSON.relative_to(ROOT)),
        "fasm": str(FASM.relative_to(ROOT)),
        "constraint": str(XDC.relative_to(ROOT)),
        "scope": "tool-based XC7A35T placement/routing and routed timing estimate only; no bitstream programming, physical board validation, or certified timing margin",
    }
    _write_report(report)

    print("RTL-016 ARTIX-7 PLACE-AND-ROUTE PASS")
    print(f"Target             : {TARGET}")
    print(f"Clock target       : {CLOCK_MHZ:.1f} MHz ({CLOCK_PERIOD_NS:.3f} ns)")
    if fmax_mhz is None:
        print("Routed Fmax        : unavailable in parsed nextpnr output")
        print("Timing result      : UNKNOWN")
    else:
        print(f"Routed Fmax        : {fmax_mhz:.3f} MHz")
        print(f"Critical path est. : {critical_path_ns:.3f} ns")
        print(f"Derived slack      : {slack_ns:+.3f} ns")
        print(f"Timing result      : {'PASS' if timing_met else 'FAIL'}")
    print(f"Report             : {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
