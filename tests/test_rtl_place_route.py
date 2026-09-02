import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_rtl_place_route.py"
REPORT = ROOT / "build" / "rtl016_timing_report.json"
XDC = ROOT / "constraints" / "radiant_daq_xc7a35t_100mhz.xdc"
IMPL_TOP = ROOT / "rtl" / "radiant_daq_impl_top.sv"


def _tool_available(name: str):
    if shutil.which(name):
        return True
    return (Path(r"C:\msys64\ucrt64\bin") / f"{name}.exe").is_file()


def test_rtl016_implementation_wrapper_and_constraint():
    wrapper = IMPL_TOP.read_text(encoding="utf-8")
    constraint = XDC.read_text(encoding="utf-8")

    assert "module radiant_daq_impl_top" in wrapper
    assert "radiant_daq_synth_top" in wrapper
    assert "cfg_channel" in wrapper
    assert "create_clock" in constraint
    assert "-period 10.000" in constraint
    assert "PACKAGE_PIN E3" in constraint


def test_rtl016_place_route_runner_reports_real_status():
    result = subprocess.run(
        [sys.executable, str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(REPORT.read_text(encoding="utf-8"))

    if not _tool_available("yosys"):
        assert report["status"] == "unavailable"
        return

    if not _tool_available("nextpnr-xilinx") or not (
        os.environ.get("RADIANT_XC7A35T_CHIPDB")
        or os.environ.get("NEXTPNR_XILINX_CHIPDB")
    ):
        assert report["status"] == "synthesized_unrouted"
        assert report["clock_target_mhz"] == 100.0
        return

    assert report["status"] == "routed"
    assert report["target"] == "XC7A35T-CSG324"
    assert report["clock_target_mhz"] == 100.0
    assert Path(ROOT / report["routed_netlist"]).is_file()
    if report["fmax_mhz"] is not None:
        assert report["fmax_mhz"] > 0
        assert report["critical_path_estimate_ns"] > 0
        assert isinstance(report["timing_met"], bool)
