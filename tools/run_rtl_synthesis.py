import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "rtl" / "yosys_rtl014.ys"
BUILD = ROOT / "build"
NETLIST = BUILD / "rtl014_synth_netlist.json"
REPORT = BUILD / "rtl014_resource_report.json"


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
    yosys, simulator_bin = find_yosys()

    if not yosys:
        report = {
            "status": "unavailable",
            "tool": "yosys",
            "top": "radiant_daq_synth_top",
            "note": "Yosys not found; no synthesis/resource counts were produced.",
        }
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("RTL-014 Yosys unavailable: resource counts not generated")
        print(f"Report: {REPORT}")
        return 0

    env = os.environ.copy()
    if simulator_bin is not None:
        env["PATH"] = str(simulator_bin) + os.pathsep + env.get("PATH", "")

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
    top = modules.get("radiant_daq_synth_top", {})
    cells = top.get("cells", {})

    by_type = {}
    for cell in cells.values():
        cell_type = cell.get("type", "unknown")
        by_type[cell_type] = by_type.get(cell_type, 0) + 1

    report = {
        "status": "synthesized",
        "tool": "yosys",
        "top": "radiant_daq_synth_top",
        "generic_cell_count": len(cells),
        "generic_cells_by_type": dict(sorted(by_type.items())),
        "netlist": str(NETLIST.relative_to(ROOT)),
        "scope": "generic synthesis only; no device mapping, placement, routing, timing closure, or physical validation",
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("RTL-014 SYNTHESIS PASS")
    print(f"Top                : {report['top']}")
    print(f"Generic cell count : {report['generic_cell_count']}")
    print(f"Netlist            : {report['netlist']}")
    print(f"Report             : {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
