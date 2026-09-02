import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_rtl_xilinx_mapping.py"
REPORT = ROOT / "build" / "rtl015_xilinx7_resource_report.json"
XDC = ROOT / "constraints" / "radiant_daq_100mhz.xdc"


def _yosys_available():
    if shutil.which("yosys"):
        return True
    return (Path(r"C:\msys64\ucrt64\bin") / "yosys.exe").is_file()


def test_rtl015_clock_constraint_declares_100mhz():
    text = XDC.read_text(encoding="utf-8")
    assert "create_clock" in text
    assert "-period 10.000" in text
    assert "[get_ports clk]" in text


def test_rtl015_xilinx7_mapping_report():
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

    if not _yosys_available():
        assert report["status"] == "unavailable"
        return

    assert report["status"] == "mapped"
    assert report["target_family"] == "xilinx_7series"
    assert report["clock_target_mhz"] == 100.0
    assert report["clock_period_ns"] == 10.0
    assert report["mapped_cell_count"] > 1
    assert report["estimated_luts"] > 0
    assert report["estimated_flip_flops"] > 0
    assert "placement" in report["scope"]
    assert "timing closure" in report["scope"]
    assert "RTL-015 XILINX-7 LOGICAL MAPPING PASS" in result.stdout
