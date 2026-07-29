"""Async serial I/O using pyserial-asyncio."""

import asyncio
import logging
from typing import Optional

import serial_asyncio
import serial

from kvmd_serial_term.config import SerialConfig

logger = logging.getLogger(__name__)


class SerialError(Exception):
    """Raised when a serial I/O operation fails."""


class SerialHandler:
    """Wraps an async serial connection with open/read/write/close operations."""

    def __init__(self, config: SerialConfig) -> None:
        self._config = config
        self._reader: "asyncio.StreamReader | None" = None
        self._writer: "asyncio.StreamWriter | None" = None

    @property
    def is_open(self) -> bool:
        return self._writer is not None

    @property
    def device(self) -> str:
        """The serial device path (e.g. /dev/ttyUSB0)."""
        return self._config.device

    @staticmethod
    def _serial_kwargs(config: SerialConfig) -> dict:
        """Map our config dataclass to pyserial keyword arguments."""
        parity_map = {
            "N": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
            "M": serial.PARITY_MARK,
            "S": serial.PARITY_SPACE,
        }
        bytesize_map = {
            5: serial.FIVEBITS,
            6: serial.SIXBITS,
            7: serial.SEVENBITS,
            8: serial.EIGHTBITS,
        }
        stopbits_map = {
            1: serial.STOPBITS_ONE,
            1.5: serial.STOPBITS_ONE_POINT_FIVE,
            2: serial.STOPBITS_TWO,
        }

        return {
            "url": config.device,
            "baudrate": config.baudrate,
            "bytesize": bytesize_map.get(config.bytesize, serial.EIGHTBITS),
            "parity": parity_map.get(config.parity, serial.PARITY_NONE),
            "stopbits": stopbits_map.get(config.stopbits, serial.STOPBITS_ONE),
            "xonxoff": config.xonxoff,
            "rtscts": config.rtscts,
            "dsrdtr": True,  # Assert DTR so the target machine knows we connected
            "exclusive": True,  # Lock the serial device
        }

    async def open(self, device_path: Optional[str] = None) -> None:
        """Open the serial port and begin reading.

        Args:
            device_path: Override the configured device path (used in tests).
        """
        kwargs = self._serial_kwargs(self._config)
        if device_path is not None:
            kwargs["url"] = device_path

        try:
            self._reader, self._writer = (
                await serial_asyncio.open_serial_connection(**kwargs)
            )
            logger.info("Opened serial port %s", kwargs["url"])
        except (serial.SerialException, OSError) as exc:
            raise SerialError(
                f"Cannot open serial port {kwargs['url']}: {exc}"
            ) from exc

    async def read(self) -> bytes:
        """Read any currently available data from the serial port.

        Returns:
            Raw bytes from the serial port, or empty bytes if nothing available.
            Does NOT block indefinitely — returns quickly with whatever is buffered.
        """
        if self._reader is None:
            raise SerialError("Cannot read: serial port is not open")

        try:
            # Read up to 4 KiB with a short timeout so we don't block the event loop
            return await asyncio.wait_for(self._reader.read(4096), timeout=0.05)
        except asyncio.TimeoutError:
            return b""

    async def write(self, data: bytes) -> None:
        """Write data to the serial port.

        Args:
            data: Raw bytes to send.
        """
        if self._writer is None:
            raise SerialError("Cannot write: serial port is not open")

        self._writer.write(data)
        await self._writer.drain()

    async def close(self) -> None:
        """Close the serial port. Safe to call multiple times."""
        if self._writer is not None:
            self._writer.close()
            self._reader = None
            self._writer = None
            logger.info("Closed serial port")
