import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RTL_FILES = [
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
]
TB = ROOT / "rtl" / "tb" / "tb_fault_tolerant_daq_node.sv"


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


def test_integrated_fault_tolerant_node_contains_transport_faults(tmp_path):
    iverilog, vvp, env = _simulator_tools()
    output = tmp_path / "fault_tolerant_node.vvp"

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
    assert (
        "PASS RTL-011 clean_event=1 crc_errors=2 protocol_errors=2 "
        "safe_entries=1 acquisition_blocked=1"
        in run_result.stdout
    )
