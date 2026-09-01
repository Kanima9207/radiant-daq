"""Optional pyserial-backed physical serial adapter for HW-004.

Provides a ``readline()`` source compatible with ``LiveSerialConsumer`` while
keeping pyserial optional. Reconnect behavior is bounded and explicit; this
module does not imply that any particular physical device or link has been
validated until measured.
"""
from dataclasses import dataclass
import time


@dataclass(frozen=True)
class SerialPortConfig:
    port: str
    baudrate: int = 115200
    timeout_s: float = 1.0
    reconnect_attempts: int = 2
    reconnect_delay_s: float = 0.25

    def __post_init__(self):
        if not isinstance(self.port, str) or not self.port.strip():
            raise ValueError("port must be a nonempty string")
        if type(self.baudrate) is not int or self.baudrate <= 0:
            raise ValueError("baudrate must be a positive integer")
        if not isinstance(self.timeout_s, (int, float)) or self.timeout_s < 0:
            raise ValueError("timeout_s must be nonnegative")
        if type(self.reconnect_attempts) is not int or self.reconnect_attempts < 0:
            raise ValueError("reconnect_attempts must be a nonnegative integer")
        if not isinstance(self.reconnect_delay_s, (int, float)) or self.reconnect_delay_s < 0:
            raise ValueError("reconnect_delay_s must be nonnegative")


class PhysicalSerialSource:
    """pyserial-compatible physical source with bounded reconnect attempts."""

    def __init__(self, config, serial_factory=None, sleep=None):
        if not isinstance(config, SerialPortConfig):
            raise TypeError("config must be SerialPortConfig")
        self.config = config
        self._sleep = time.sleep if sleep is None else sleep
        if not callable(self._sleep):
            raise TypeError("sleep must be callable")
        self._serial_factory = serial_factory or self._default_serial_factory
        if not callable(self._serial_factory):
            raise TypeError("serial_factory must be callable")
        self._serial = None
        self.connect_count = 0
        self.reconnect_count = 0
        self.last_error = None

    @staticmethod
    def _default_serial_factory(**kwargs):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "pyserial is required for physical serial access; install radiant-daq[serial]"
            ) from exc
        return serial.Serial(**kwargs)

    @property
    def is_open(self):
        if self._serial is None:
            return False
        return bool(getattr(self._serial, "is_open", True))

    def open(self):
        if self.is_open:
            return self
        self._serial = self._serial_factory(
            port=self.config.port,
            baudrate=self.config.baudrate,
            timeout=float(self.config.timeout_s),
        )
        self.connect_count += 1
        self.last_error = None
        return self

    def close(self):
        if self._serial is not None:
            close = getattr(self._serial, "close", None)
            if callable(close):
                close()
        self._serial = None

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def readline(self):
        attempts = 0
        while True:
            try:
                if not self.is_open:
                    self.open()
                data = self._serial.readline()
                if not isinstance(data, (bytes, bytearray)):
                    raise TypeError("serial readline() must return bytes")
                self.last_error = None
                return bytes(data)
            except Exception as exc:
                self.last_error = str(exc)
                self.close()
                if attempts >= self.config.reconnect_attempts:
                    raise
                attempts += 1
                self.reconnect_count += 1
                if self.config.reconnect_delay_s:
                    self._sleep(float(self.config.reconnect_delay_s))
