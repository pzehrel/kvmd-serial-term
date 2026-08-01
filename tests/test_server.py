"""Integration tests for the aiohttp server — start server, connect WS, end-to-end relay."""

import asyncio
import json
import os
import select
import tempfile

import pytest
from aiohttp import ClientSession, UnixConnector, WSMsgType

from kvmd_serial_term.config import SerialConfig, ServerConfig
from kvmd_serial_term.serial_handler import SerialHandler
from kvmd_serial_term.server import SerialTermServer
from tests.conftest import make_pty_pair


@pytest.fixture
def temp_socket():
    """A temporary Unix socket path."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".sock") as f:
        path = f.name
    os.unlink(path)  # Server creates it
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_server_serves_index_html(temp_socket):
    """The HTTP endpoint / returns the terminal HTML page."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    await handler.open()

    server_config = ServerConfig(unix_socket=temp_socket)
    server = SerialTermServer(server_config, handler)
    await server.start()

    try:
        conn = _unix_connector(temp_socket)
        async with ClientSession(connector=conn) as session, session.get("http://localhost/") as resp:
            assert resp.status == 200
            body = await resp.text()
            assert "<!DOCTYPE html>" in body
            assert "xterm" in body
    finally:
        await server.stop()
        await handler.close()
        os.close(master_fd)


@pytest.mark.asyncio
async def test_websocket_keypress_to_pty(temp_socket):
    """Keystrokes sent over WebSocket arrive at the PTY master as raw bytes."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    await handler.open()

    server_config = ServerConfig(unix_socket=temp_socket)
    server = SerialTermServer(server_config, handler)
    await server.start()

    try:
        conn = _unix_connector(temp_socket)
        async with ClientSession(connector=conn) as session, session.ws_connect("http://localhost/ws") as ws:
            # Wait for relay to signal it's ready (replaces magic sleep)
            await server._relay.started.wait()

            # Send a keystroke — need one event-loop tick for
            # _ws_input_loop to receive and forward it to serial
            await ws.send_str("ls -la\n")
            await asyncio.sleep(0.05)

            # Read from PTY master (non-blocking)
            ready, _, _ = select.select([master_fd], [], [], 0.5)
            assert master_fd in ready, "PTY master should have received data"
            data = os.read(master_fd, 1024)
            assert b"ls -la\n" in data
    finally:
        await server.stop()
        await handler.close()
        os.close(master_fd)


@pytest.mark.asyncio
async def test_websocket_receives_pty_output(temp_socket):
    """Data written to the PTY master arrives at the WebSocket client."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    await handler.open()

    server_config = ServerConfig(unix_socket=temp_socket)
    server = SerialTermServer(server_config, handler)
    await server.start()

    try:
        conn = _unix_connector(temp_socket)
        async with ClientSession(connector=conn) as session, session.ws_connect("http://localhost/ws") as ws:
            # Consume the session "active" notification
            msg = await ws.receive(timeout=2)
            assert msg.type == WSMsgType.TEXT
            assert '"active"' in msg.data

            # Wait for relay to finish kick + start reading
            await server._relay.started.wait()

            # Now the relay is running — write to PTY
            os.write(master_fd, b"hello from serial\n")
            await asyncio.sleep(0.1)

            # Wait for the relay to forward to WebSocket
            msg = await ws.receive(timeout=2)
            assert msg.type == WSMsgType.TEXT
            assert "hello from serial" in msg.data

            await ws.close()
    finally:
        await server.stop()
        await handler.close()
        os.close(master_fd)


@pytest.mark.asyncio
async def test_websocket_resize_message_does_not_crash(temp_socket):
    """Sending a JSON resize frame should be handled without errors."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    await handler.open()

    server_config = ServerConfig(unix_socket=temp_socket)
    server = SerialTermServer(server_config, handler)
    await server.start()

    try:
        conn = _unix_connector(temp_socket)
        async with ClientSession(connector=conn) as session, session.ws_connect("http://localhost/ws") as ws:
            await ws.send_str('{"type":"resize","rows":24,"cols":80}')
            await asyncio.sleep(0.1)
            assert not ws.closed

            await ws.send_str("A")
            await asyncio.sleep(0.1)
            assert not ws.closed

            await ws.close()
    finally:
        await server.stop()
        await handler.close()
        os.close(master_fd)


@pytest.mark.asyncio
async def test_server_static_files(temp_socket):
    """Static files (xterm.js, xterm.css) are served."""
    _, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    await handler.open()

    server_config = ServerConfig(unix_socket=temp_socket)
    server = SerialTermServer(server_config, handler)
    await server.start()

    try:
        conn = _unix_connector(temp_socket)
        async with ClientSession(connector=conn) as session:
            async with session.get("http://localhost/static/xterm.js") as resp:
                assert resp.status == 200
                body = await resp.text()
                assert "Terminal" in body

            async with session.get("http://localhost/static/xterm.css") as resp:
                assert resp.status == 200
                body = await resp.text()
                assert ".xterm" in body
    finally:
        await server.stop()
        await handler.close()


def _unix_connector(socket_path: str):
    """Create an aiohttp UnixConnector for the given socket path."""
    return UnixConnector(path=socket_path)


@pytest.mark.asyncio
async def test_full_stack_session_queue(temp_socket):
    """End-to-end: first client gets serial, second client queues, then is promoted."""
    master_fd, slave_name = make_pty_pair()
    handler = SerialHandler(SerialConfig(device=slave_name))
    await handler.open()

    server_config = ServerConfig(unix_socket=temp_socket)
    server = SerialTermServer(server_config, handler)
    await server.start()

    conn1 = _unix_connector(temp_socket)
    conn2 = _unix_connector(temp_socket)
    session1 = ClientSession(connector=conn1)
    session2 = ClientSession(connector=conn2)

    try:
        # ── Client 1 connects: should be active ──────────────────────────
        ws1 = await session1.ws_connect("http://localhost/ws")
        msg = await ws1.receive(timeout=2)
        assert msg.type == WSMsgType.TEXT
        data1 = json.loads(msg.data)
        assert data1["type"] == "active"

        # Wait for relay to signal it's ready
        await server._relay.started.wait()

        # Client 1 sends keystrokes → they reach the PTY
        await ws1.send_str("echo hello\n")
        await asyncio.sleep(0.1)
        ready, _, _ = select.select([master_fd], [], [], 0.5)
        assert master_fd in ready
        buf = os.read(master_fd, 1024)
        assert b"echo hello\n" in buf

        # ── Client 2 connects: should be queued ──────────────────────────
        ws2 = await session2.ws_connect("http://localhost/ws")
        msg = await ws2.receive(timeout=2)
        assert msg.type == WSMsgType.TEXT
        data2 = json.loads(msg.data)
        assert data2["type"] == "queue"
        assert data2["position"] == 1

        # Client 2's keystrokes should NOT reach the PTY (queued)
        await ws2.send_str("should not arrive\n")
        await asyncio.sleep(0.1)
        if select.select([master_fd], [], [], 0.3)[0]:
            os.read(master_fd, 4096)
        await ws2.send_str("X")
        await asyncio.sleep(0.1)
        ready, _, _ = select.select([master_fd], [], [], 0.3)
        if ready:
            leftover = os.read(master_fd, 4096)
            assert b"should not arrive" not in leftover, (
                "Queued client keystrokes must not reach serial"
            )

        # ── Client 1 disconnects ─────────────────────────────────────────
        await ws1.close()
        await session1.close()

        # Give the server time to promote client 2 (async create_task)
        await asyncio.sleep(0.3)

        # ── Client 2 should be promoted ──────────────────────────────────
        msg = await ws2.receive(timeout=3)
        assert msg.type == WSMsgType.TEXT, f"Expected TEXT, got {msg.type}"
        promo = json.loads(msg.data)
        assert promo["type"] == "active", f"Expected active, got {promo}"

        # Wait for the NEW relay to signal it's ready
        await server._relay.started.wait()

        # Now client 2's keystrokes should reach the PTY
        await ws2.send_str("now active\n")
        await asyncio.sleep(0.1)
        ready, _, _ = select.select([master_fd], [], [], 0.5)
        assert master_fd in ready, "Promoted client keystrokes should reach PTY"
        buf = os.read(master_fd, 1024)
        assert b"now active\n" in buf, (
            f"Promoted client keystrokes must reach serial, got {buf!r}"
        )

        await ws2.close()
        await session2.close()
    finally:
        await server.stop()
        await handler.close()
        await asyncio.gather(session1.close(), session2.close(), return_exceptions=True)
        os.close(master_fd)
