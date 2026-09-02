import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RTL_RECEIVER = ROOT / "rtl" / "event_packet_receiver.sv"
RTL_SEQUENCE = ROOT / "rtl" / "event_sequence_monitor.sv"
RTL_MONITORED = ROOT / "rtl" / "monitored_event_packet_receiver.sv"
RTL_HEALTH = ROOT / "rtl" / "link_health_monitor.sv"
RTL_HEALTH_WRAPPER = ROOT / "rtl" / "health_monitored_event_packet_receiver.sv"
RTL_SAFE = ROOT / "rtl" / "safe_state_controller.sv"
TB = ROOT / "rtl" / "tb" / "tb_random_fault_campaign.sv"


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


def test_randomized_long_run_fault_detection_and_containment(tmp_path):
    iverilog, vvp, env = _simulator_tools()
    output = tmp_path / "random_fault_campaign.vvp"

    compile_result = subprocess.run(
        [
            iverilog,
            "-g2012",
            "-o",
            str(output),
            str(RTL_RECEIVER),
            str(RTL_SEQUENCE),
            str(RTL_MONITORED),
            str(RTL_HEALTH),
            str(RTL_HEALTH_WRAPPER),
            str(RTL_SAFE),
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
    assert (
        "PASS RTL-013 randomized_trials=600 detection_pct=100 "
        "containment_pct=100 false_alarms=0"
        in run_result.stdout
    )
    assert "RANDOM CAMPAIGN RTL-013 seed=0x1ACEB00C trials=600" in run_result.stdout
    assert "CLASS COUNTS clean=" in run_result.stdout
