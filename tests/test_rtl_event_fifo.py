import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RTL_TIMEBASE = ROOT / "rtl" / "acquisition_timebase.sv"
RTL_TRIGGER = ROOT / "rtl" / "threshold_trigger.sv"
RTL_MULTI = ROOT / "rtl" / "multi_channel_acquisition_pipeline.sv"
RTL_FIFO = ROOT / "rtl" / "event_fifo.sv"
RTL_BUFFERED = ROOT / "rtl" / "buffered_multi_channel_pipeline.sv"
TB = ROOT / "rtl" / "tb" / "tb_buffered_multi_channel_pipeline.sv"


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


def test_event_fifo_backpressure_preserves_multichannel_events(tmp_path):
    iverilog, vvp, env = _simulator_tools()
    output = tmp_path / "event_fifo.vvp"

    compile_result = subprocess.run(
        [
            iverilog,
            "-g2012",
            "-o",
            str(output),
            str(RTL_TIMEBASE),
            str(RTL_TRIGGER),
            str(RTL_MULTI),
            str(RTL_FIFO),
            str(RTL_BUFFERED),
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
        "PASS RTL-005 fifo_depth=2 events=4 order=CH0_CH1_CH2_CH3 backpressure=held"
        in run_result.stdout
    )
