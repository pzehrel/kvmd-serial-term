"""Tests for the async serial handler — uses PTY pairs instead of real serial devices."""

import asyncio
import os

import pytest

from kvmd_serial_term.config import SerialConfig
from kvmd_serial_term.serial_handler import SerialError, SerialHandler
from tests.conftest import make_pty_pair


def _make_config(device_path: str) -> SerialConfig:
    return SerialConfig(device=device_path)


@pytest.mark.asyncio
async def test_open_close():
    """Handler can open and close a PTY without errors."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(_make_config(slave_name))

    await handler.open()
    assert handler.is_open is True

    await handler.close()
    assert handler.is_open is False
    os.close(master_fd)


@pytest.mark.asyncio
async def test_write_read_roundtrip():
    """Data written by the handler arrives at the PTY master, and vice versa."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(_make_config(slave_name))
    await handler.open()

    # Handler writes → master side reads
    await handler.write(b"hello\n")
    # Read from master with a small timeout-based poll
    data = await asyncio.get_event_loop().run_in_executor(
        None, lambda: os.read(master_fd, 1024)
    )
    assert data == b"hello\n"

    # Master writes → handler reads
    os.write(master_fd, b"world\n")
    await asyncio.sleep(0.05)  # let the data propagate
    received = await handler.read()
    assert b"world\n" in received

    await handler.close()
    os.close(master_fd)


@pytest.mark.asyncio
async def test_read_returns_empty_when_no_data():
    """read() times out quickly and returns empty bytes when nothing is available."""
    _, slave_name = make_pty_pair()
    handler = SerialHandler(_make_config(slave_name))
    await handler.open()

    data = await handler.read()
    assert data == b""

    await handler.close()


@pytest.mark.asyncio
async def test_open_nonexistent_device_raises():
    """Opening a nonexistent device path raises SerialError."""
    handler = SerialHandler(_make_config("/dev/nonexistent_serial_device_xyz"))
    with pytest.raises(SerialError, match="[Cc]annot open|[Ff]ailed to open|not found"):
        await handler.open()


@pytest.mark.asyncio
async def test_close_twice_is_idempotent():
    """Calling close() on an already-closed handler is safe."""
    _, slave_name = make_pty_pair()
    handler = SerialHandler(_make_config(slave_name))
    await handler.open()
    await handler.close()
    # Second close should not raise
    await handler.close()


@pytest.mark.asyncio
async def test_write_when_closed_raises():
    """Writing to a closed handler raises SerialError."""
    _, slave_name = make_pty_pair()
    handler = SerialHandler(_make_config(slave_name))
    await handler.open()
    await handler.close()

    with pytest.raises(SerialError, match="[Nn]ot open"):
        await handler.write(b"test")
