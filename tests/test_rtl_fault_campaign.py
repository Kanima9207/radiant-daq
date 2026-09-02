import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RTL_FILES = [
    ROOT / "rtl" / "event_packet_receiver.sv",
    ROOT / "rtl" / "event_sequence_monitor.sv",
    ROOT / "rtl" / "monitored_event_packet_receiver.sv",
    ROOT / "rtl" / "link_health_monitor.sv",
    ROOT / "rtl" / "health_monitored_event_packet_receiver.sv",
    ROOT / "rtl" / "safe_state_controller.sv",
]
TB = ROOT / "rtl" / "tb" / "tb_fault_campaign.sv"


def _simulator_tools():
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    simulator_bin = None

    if not iverilog or not vvp:
        msys2_bin = Path(r"C:\msys64\ucrt64\bin")
        candidate_iverilog = msys2_bin / "iverilog.exe"
        candidate_vvp = msys2_bin / "vvp.exe"
        if candidate_iverilog.is_file() and candidate_vvp.is_file():
            iverilog = str(candidate_iverilog)
            vvp = str(candidate_vvp)
            simulator_bin = msys2_bin

    if not iverilog or not vvp:
        pytest.skip("Icarus Verilog not found on PATH or in C:\\msys64\\ucrt64\\bin")

    env = os.environ.copy()
    if simulator_bin is not None:
        env["PATH"] = str(simulator_bin) + os.pathsep + env.get("PATH", "")

    return iverilog, vvp, env


def test_end_to_end_transport_fault_campaign(tmp_path):
    iverilog, vvp, env = _simulator_tools()
    output = tmp_path / "fault_campaign.vvp"

    compile_result = subprocess.run(
        [
            iverilog,
            "-g2012",
            "-o",
            str(output),
            *(str(path) for path in RTL_FILES),
            str(TB),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr

    run_result = subprocess.run(
        [vvp, str(output)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert run_result.returncode == 0, run_result.stdout + run_result.stderr
    assert "PASS RTL-012 crc=1 protocol=1 drop=1 duplicate=1 reorder=1 silence=1" in run_result.stdout

    match = re.search(
        r"CAMPAIGN RTL-012 scenarios=(\d+) detected=(\d+) contained=(\d+) "
        r"detection_pct=(\d+) containment_pct=(\d+)",
        run_result.stdout,
    )
    assert match, run_result.stdout
    assert tuple(map(int, match.groups())) == (6, 6, 6, 100, 100)
