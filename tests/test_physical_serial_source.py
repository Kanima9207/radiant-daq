import pytest

from radiant.hardware import PhysicalSerialSource, SerialPortConfig


class FakeSerial:
    def __init__(self, lines=None, fail_reads=0):
        self.lines = list(lines or [b"ok\n"])
        self.fail_reads = fail_reads
        self.is_open = True
        self.closed = False

    def readline(self):
        if self.fail_reads:
            self.fail_reads -= 1
            raise OSError("link lost")
        return self.lines.pop(0) if self.lines else b""

    def close(self):
        self.is_open = False
        self.closed = True


class Factory:
    def __init__(self, serials):
        self.serials = list(serials)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        serial = self.serials.pop(0)
        serial.is_open = True
        return serial


def test_config_validation():
    with pytest.raises(ValueError):
        SerialPortConfig("")
    with pytest.raises(ValueError):
        SerialPortConfig("COM3", baudrate=0)
    with pytest.raises(ValueError):
        SerialPortConfig("COM3", timeout_s=-1)


def test_open_passes_port_baud_timeout():
    factory = Factory([FakeSerial()])
    source = PhysicalSerialSource(SerialPortConfig("COM7", 230400, 0.5), factory)
    source.open()
    assert factory.calls == [{"port": "COM7", "baudrate": 230400, "timeout": 0.5}]
    assert source.is_open


def test_readline_returns_bytes():
    source = PhysicalSerialSource(SerialPortConfig("COM1"), Factory([FakeSerial([b"frame\n"])]))
    assert source.readline() == b"frame\n"


def test_close_closes_port():
    serial = FakeSerial()
    source = PhysicalSerialSource(SerialPortConfig("COM1"), Factory([serial]))
    source.open()
    source.close()
    assert serial.closed
    assert not source.is_open


def test_context_manager_opens_and_closes():
    serial = FakeSerial()
    source = PhysicalSerialSource(SerialPortConfig("COM1"), Factory([serial]))
    with source as opened:
        assert opened.is_open
    assert serial.closed


def test_read_failure_reconnects_and_recovers():
    first = FakeSerial(fail_reads=1)
    second = FakeSerial([b"recovered\n"])
    factory = Factory([first, second])
    source = PhysicalSerialSource(
        SerialPortConfig("COM1", reconnect_attempts=1, reconnect_delay_s=0),
        factory,
    )
    assert source.readline() == b"recovered\n"
    assert source.reconnect_count == 1
    assert source.connect_count == 2


def test_reconnect_exhaustion_raises():
    factory = Factory([FakeSerial(fail_reads=1), FakeSerial(fail_reads=1)])
    source = PhysicalSerialSource(
        SerialPortConfig("COM1", reconnect_attempts=1, reconnect_delay_s=0),
        factory,
    )
    with pytest.raises(OSError):
        source.readline()
    assert source.reconnect_count == 1
    assert source.last_error == "link lost"


def test_nonbyte_serial_result_reconnects_then_raises():
    class BadSerial(FakeSerial):
        def readline(self):
            return "text"
    factory = Factory([BadSerial(), BadSerial()])
    source = PhysicalSerialSource(
        SerialPortConfig("COM1", reconnect_attempts=1, reconnect_delay_s=0),
        factory,
    )
    with pytest.raises(TypeError):
        source.readline()


def test_open_is_idempotent():
    factory = Factory([FakeSerial()])
    source = PhysicalSerialSource(SerialPortConfig("COM1"), factory)
    source.open()
    source.open()
    assert source.connect_count == 1


def test_invalid_constructor_arguments():
    with pytest.raises(TypeError):
        PhysicalSerialSource("COM1")
    with pytest.raises(TypeError):
        PhysicalSerialSource(SerialPortConfig("COM1"), serial_factory=1)
    with pytest.raises(TypeError):
        PhysicalSerialSource(SerialPortConfig("COM1"), sleep=1)
