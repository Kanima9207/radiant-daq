import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TOP = ROOT / "rtl" / "radiant_daq_synth_top.sv"
RUNNER = ROOT / "tools" / "run_rtl_synthesis.py"

SOURCES = [
    ROOT / "rtl" / "acquisition_timebase.sv",
    ROOT / "rtl" / "threshold_trigger.sv",
    ROOT / "rtl" / "multi_channel_acquisition_pipeline.sv",
    ROOT / "rtl" / "event_fifo.sv",
    ROOT / "rtl" / "buffered_multi_channel_pipeline.sv",
    ROOT / "rtl" / "event_packetizer.sv",
    ROOT / "rtl" / "packetized_multi_channel_pipeline.sv",
    ROOT / "rtl" / "event_packet_receiver.sv",
    ROOT / "rtl" / "event_sequence_monitor.sv",
    ROOT / "rtl" / "monitored_event_packet_receiver.sv",
    ROOT / "rtl" / "link_health_monitor.sv",
    ROOT / "rtl" / "health_monitored_event_packet_receiver.sv",
    ROOT / "rtl" / "safe_state_controller.sv",
    ROOT / "rtl" / "fault_tolerant_daq_node.sv",
    TOP,
]


def _iverilog_tools():
    iverilog = shutil.which("iverilog")
    simulator_bin = None
    if not iverilog:
        msys2_bin = Path(r"C:\msys64\ucrt64\bin")
        candidate = msys2_bin / "iverilog.exe"
        if candidate.is_file():
            iverilog = str(candidate)
            simulator_bin = msys2_bin
    if not iverilog:
        pytest.fail("Icarus Verilog not found; prior RTL regressions require it")
    env = os.environ.copy()
    if simulator_bin is not None:
        env["PATH"] = str(simulator_bin) + os.pathsep + env.get("PATH", "")
    return iverilog, env


def test_synthesis_top_elaborates_complete_hierarchy(tmp_path):
    iverilog, env = _iverilog_tools()
    output = tmp_path / "rtl014_elaboration.vvp"
    result = subprocess.run(
        [iverilog, "-g2012", "-s", "radiant_daq_synth_top", "-o", str(output), *map(str, SOURCES)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.is_file()


def test_synthesis_runner_reports_real_status():
    result = subprocess.run(
        [sys.executable, str(RUNNER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    report_path = ROOT / "build" / "rtl014_resource_report.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["top"] == "radiant_daq_synth_top"
    assert report["status"] in {"unavailable", "synthesized"}

    if report["status"] == "synthesized":
        assert report["tool"] == "yosys"
        assert isinstance(report["generic_cell_count"], int)
        assert report["generic_cell_count"] > 0
        assert (ROOT / report["netlist"]).is_file()
    else:
        assert "no synthesis/resource counts" in report["note"].lower()
