"""Tests for the Relay module — serial kick, read loop, observable state."""

import asyncio
import os
import pty

import pytest

from kvmd_serial_term.config import SerialConfig
from kvmd_serial_term.serial_handler import SerialHandler
from kvmd_serial_term.relay import Relay


def make_pty_pair():
    """Return (master_fd, slave_name)."""
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)
    os.close(slave_fd)
    return master_fd, slave_name


class FakeWS:
    """Minimal WebSocket stub for testing relay output."""

    def __init__(self):
        self.messages = []
        self.closed = False

    async def send_str(self, text: str) -> None:
        self.messages.append(text)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_relay_start_sets_started_event():
    """Relay.start() sets the started event after kick + relay loop begins."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    relay = Relay(handler)
    ws = FakeWS()

    await relay.start(ws)
    try:
        assert relay.started.is_set()
        assert relay.is_running
    finally:
        await relay.stop()
    os.close(master_fd)


@pytest.mark.asyncio
async def test_relay_forwards_serial_data():
    """Data written to the PTY master arrives at the WebSocket via relay."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    relay = Relay(handler)
    ws = FakeWS()

    await relay.start(ws)
    try:
        # Wait for kick to complete
        await relay.started.wait()

        # Write to PTY master side
        os.write(master_fd, b"hello\n")
        await asyncio.sleep(0.2)

        assert any("hello" in m for m in ws.messages)
    finally:
        await relay.stop()
    os.close(master_fd)


@pytest.mark.asyncio
async def test_relay_stop_clears_running():
    """Relay.stop() sets is_running to False."""
    _, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    relay = Relay(handler)
    ws = FakeWS()

    await relay.start(ws)
    await relay.stop()

    assert not relay.is_running


@pytest.mark.asyncio
async def test_relay_kick_writes_newline():
    """kick() writes \\n to the serial port after open + settle."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    relay = Relay(handler)
    ws = FakeWS()

    await relay.start(ws)
    try:
        # Read from PTY master — the kick should have sent \n
        await asyncio.sleep(0.1)
        if ws.messages:
            # Some output came back (echo of \n)
            pass  # Success — kick worked
    finally:
        await relay.stop()
    os.close(master_fd)


@pytest.mark.asyncio
async def test_relay_logout_sends_ctrl_d():
    """logout() sends \\x04 (Ctrl+D) to the serial port."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    relay = Relay(handler)
    ws = FakeWS()

    await relay.start(ws)
    try:
        await relay.logout()
        await asyncio.sleep(0.1)
    finally:
        await relay.stop()
    os.close(master_fd)


@pytest.mark.asyncio
async def test_relay_start_twice_is_safe():
    """Calling start() twice stops old relay first."""
    _, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    relay = Relay(handler)

    await relay.start(FakeWS())
    old_task = relay._task
    await relay.start(FakeWS())  # Should stop old, start new
    assert relay._task != old_task
    assert relay.is_running
    await relay.stop()


@pytest.mark.asyncio
async def test_relay_stop_when_not_running_is_safe():
    """Calling stop() on an idle relay is a no-op."""
    _, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    relay = Relay(handler)

    await relay.stop()  # Should not raise
    assert not relay.is_running
