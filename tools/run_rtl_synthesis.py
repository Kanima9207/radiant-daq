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
TOP = "radiant_daq_synth_top"


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
            "top": TOP,
            "note": "Yosys not found; no synthesis/resource counts were produced.",
        }
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("RTL-014B Yosys unavailable: resource counts not generated")
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
    top = modules.get(TOP, {})
    cells = top.get("cells", {})

    by_type = {}
    hierarchical_cells = []
    for name, cell in cells.items():
        cell_type = cell.get("type", "unknown")
        by_type[cell_type] = by_type.get(cell_type, 0) + 1
        if cell_type.startswith("$paramod") or cell_type in modules:
            hierarchical_cells.append({"name": name, "type": cell_type})

    flattened = len(hierarchical_cells) == 0
    report = {
        "status": "synthesized" if flattened else "hierarchy_remaining",
        "tool": "yosys",
        "top": TOP,
        "flattened": flattened,
        "generic_cell_count": len(cells),
        "generic_cells_by_type": dict(sorted(by_type.items())),
        "hierarchical_cells_remaining": hierarchical_cells,
        "netlist": str(NETLIST.relative_to(ROOT)),
        "scope": "flattened generic synthesis only; no device mapping, placement, routing, timing closure, or physical validation",
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if not flattened:
        print("RTL-014B SYNTHESIS INCOMPLETE: hierarchy remains after flatten")
        print(f"Report             : {REPORT.relative_to(ROOT)}")
        return 2
    if not cells:
        print("RTL-014B SYNTHESIS INCOMPLETE: flattened design contains no generic cells")
        return 3

    print("RTL-014B FLATTENED SYNTHESIS PASS")
    print(f"Top                : {report['top']}")
    print(f"Flattened          : {report['flattened']}")
    print(f"Generic cell count : {report['generic_cell_count']}")
    print(f"Cell types         : {len(report['generic_cells_by_type'])}")
    print(f"Netlist            : {report['netlist']}")
    print(f"Report             : {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
