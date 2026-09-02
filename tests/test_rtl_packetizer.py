import os
import re
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
]
TB = ROOT / "rtl" / "tb" / "tb_packetized_multi_channel_pipeline.sv"


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


def _crc32_msb(payload: int, width: int = 224) -> int:
    """Independent software reference for the RTL-006 CRC convention."""
    crc = 0xFFFFFFFF
    polynomial = 0x04C11DB7

    for bit_index in range(width - 1, -1, -1):
        data_bit = (payload >> bit_index) & 1
        feedback = ((crc >> 31) & 1) ^ data_bit
        crc = (crc << 1) & 0xFFFFFFFF
        if feedback:
            crc ^= polynomial

    return crc ^ 0xFFFFFFFF


def _extract_packet(stdout: str, label: str) -> int:
    match = re.search(rf"^{label}=([0-9a-fA-F]{{64}})$", stdout, re.MULTILINE)
    assert match, f"{label} not found in simulator output:\n{stdout}"
    return int(match.group(1), 16)


def _assert_packet_crc(packet: int) -> None:
    payload = packet >> 32
    transmitted_crc = packet & 0xFFFFFFFF
    assert transmitted_crc == _crc32_msb(payload)


def test_packetizer_frame_sequence_backpressure_and_crc(tmp_path):
    iverilog, vvp, env = _simulator_tools()
    output = tmp_path / "packetizer.vvp"

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
    assert "PASS RTL-006 packets=2 crc32=IEEE_MSB backpressure=stable" in run_result.stdout

    packet0 = _extract_packet(run_result.stdout, "PACKET0")
    packet1 = _extract_packet(run_result.stdout, "PACKET1")

    _assert_packet_crc(packet0)
    _assert_packet_crc(packet1)

    # Independent framing checks in Python, separate from the HDL testbench.
    assert (packet0 >> 240) & 0xFFFF == 0x5244
    assert (packet0 >> 232) & 0xFF == 0x01
    assert (packet0 >> 224) & 0xFF == 0x01
    assert (packet0 >> 192) & 0xFFFFFFFF == 0
    assert (packet0 >> 184) & 0xFF == 2
    assert (packet0 >> 112) & 0xFFFFFFFFFFFFFFFF == 1
    assert (packet0 >> 48) & 0xFFFFFFFFFFFFFFFF == 20_000
    assert (packet0 >> 32) & 0xFFFF == 1_200

    assert (packet1 >> 192) & 0xFFFFFFFF == 1
    assert (packet1 >> 184) & 0xFF == 0
    assert (packet1 >> 112) & 0xFFFFFFFFFFFFFFFF == 3
    assert (packet1 >> 48) & 0xFFFFFFFFFFFFFFFF == 60_000
    assert (packet1 >> 32) & 0xFFFF == 1_300
