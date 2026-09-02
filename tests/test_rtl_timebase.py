import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RTL = ROOT / "rtl" / "acquisition_timebase.sv"
TB = ROOT / "rtl" / "tb" / "tb_acquisition_timebase.sv"


def _simulator_tools():
    iverilog = shutil.which("iverilog")
    vvp = shutil.which("vvp")

    # Windows/MSYS2 fallback: allow the tests to find a standard UCRT64
    # installation even when C:\\msys64\\ucrt64\\bin is not on PowerShell PATH.
    if not iverilog or not vvp:
        msys2_bin = Path(r"C:\msys64\ucrt64\bin")
        candidate_iverilog = msys2_bin / "iverilog.exe"
        candidate_vvp = msys2_bin / "vvp.exe"
        if candidate_iverilog.is_file() and candidate_vvp.is_file():
            iverilog = str(candidate_iverilog)
            vvp = str(candidate_vvp)

    if not iverilog or not vvp:
        pytest.skip("Icarus Verilog not found on PATH or in C:\\msys64\\ucrt64\\bin")
    return iverilog, vvp


@pytest.mark.parametrize("sample_rate_hz", [50_000, 48_000])
def test_acquisition_timebase_matches_reference(sample_rate_hz, tmp_path):
    iverilog, vvp = _simulator_tools()
    output = tmp_path / "timebase.vvp"

    compile_result = subprocess.run(
        [
            iverilog,
            "-g2012",
            f"-Ptb_acquisition_timebase.SAMPLE_RATE_HZ={sample_rate_hz}",
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
    assert f"PASS RTL-001 SAMPLE_RATE_HZ={sample_rate_hz}" in run_result.stdout
