import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "rtl" / "threshold_trigger.sv"
TB = ROOT / "rtl" / "tb" / "tb_threshold_trigger.sv"


def _simulator_tools():
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")
    if not iverilog or not vvp:
        pytest.skip("Icarus Verilog not installed; RTL simulation skipped")
    return iverilog, vvp


def test_threshold_trigger_hysteresis_holdoff_and_metadata(tmp_path):
    iverilog, vvp = _simulator_tools()
    output = tmp_path / "trigger.vvp"

    compile_result = subprocess.run(
        [
            iverilog,
            "-g2012",
            "-o",
            str(output),
            str(RTL),
            str(TB),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stderr

    run_result = subprocess.run(
        [vvp, str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run_result.returncode == 0, run_result.stdout + run_result.stderr
    assert "PASS RTL-002 triggers=2 holdoff=3" in run_result.stdout
