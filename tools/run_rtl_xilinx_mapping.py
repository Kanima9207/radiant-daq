import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "rtl" / "yosys_rtl015_xilinx7.ys"
BUILD = ROOT / "build"
NETLIST = BUILD / "rtl015_xilinx7_netlist.json"
REPORT = BUILD / "rtl015_xilinx7_resource_report.json"
TOP = "radiant_daq_synth_top"
CLOCK_MHZ = 100.0
CLOCK_PERIOD_NS = 10.0


def find_yosys():
    candidate = shutil.which("yosys")
    if candidate:
        return candidate, None

    msys2_bin = Path(r"C:\msys64\ucrt64\bin")
    exe = msys2_bin / "yosys.exe"
    if exe.is_file():
        return str(exe), msys2_bin
    return None, None


def main():
    BUILD.mkdir(exist_ok=True)
    yosys, msys2_bin = find_yosys()
    if not yosys:
        report = {
            "status": "unavailable",
            "tool": "yosys",
            "target_family": "xilinx_7series",
            "top": TOP,
            "clock_target_mhz": CLOCK_MHZ,
            "clock_period_ns": CLOCK_PERIOD_NS,
            "note": "Yosys not found; no Xilinx logical mapping was produced.",
        }
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("RTL-015 Yosys unavailable: Xilinx mapping not generated")
        return 0

    env = os.environ.copy()
    if msys2_bin is not None:
        env["PATH"] = str(msys2_bin) + os.pathsep + env.get("PATH", "")

    result = subprocess.run(
        [yosys, "-s", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode

    netlist = json.loads(NETLIST.read_text(encoding="utf-8"))
    modules = netlist.get("modules", {})
    top = modules.get(TOP, {})
    cells = top.get("cells", {})

    by_type = {}
    for cell in cells.values():
        cell_type = cell.get("type", "unknown")
        by_type[cell_type] = by_type.get(cell_type, 0) + 1

    lut_count = sum(count for name, count in by_type.items() if name.startswith("LUT"))
    ff_count = sum(count for name, count in by_type.items() if name.startswith("FD"))
    carry4_count = by_type.get("CARRY4", 0)
    muxf_count = sum(count for name, count in by_type.items() if name.startswith("MUXF"))

    report = {
        "status": "mapped",
        "tool": "yosys",
        "target_family": "xilinx_7series",
        "top": TOP,
        "clock_target_mhz": CLOCK_MHZ,
        "clock_period_ns": CLOCK_PERIOD_NS,
        "mapped_cell_count": len(cells),
        "estimated_luts": lut_count,
        "estimated_flip_flops": ff_count,
        "carry4": carry4_count,
        "muxf": muxf_count,
        "mapped_cells_by_type": dict(sorted(by_type.items())),
        "netlist": str(NETLIST.relative_to(ROOT)),
        "constraint": "constraints\\radiant_daq_100mhz.xdc",
        "scope": "logical Xilinx 7-series mapping only; no placement, routing, static timing analysis, timing closure, bitstream generation, or physical validation",
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("RTL-015 XILINX-7 LOGICAL MAPPING PASS")
    print(f"Top                : {TOP}")
    print(f"Clock target       : {CLOCK_MHZ:.1f} MHz ({CLOCK_PERIOD_NS:.3f} ns)")
    print(f"Mapped cell count  : {len(cells)}")
    print(f"Estimated LUTs     : {lut_count}")
    print(f"Estimated FFs      : {ff_count}")
    print(f"CARRY4             : {carry4_count}")
    print(f"MUXF               : {muxf_count}")
    print(f"Report             : {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
