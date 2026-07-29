"""aiohttp server: HTTP page + WebSocket ↔ serial relay with client management."""

import asyncio
import json
import logging
import os
import pathlib

from aiohttp import web

from kvmd_serial_term.config import ServerConfig
from kvmd_serial_term.serial_handler import SerialHandler
from kvmd_serial_term.client import ClientManager

logger = logging.getLogger(__name__)


async def _close_ws_safe(ws: web.WebSocketResponse) -> None:
    """Close a WebSocket connection, timing out after 1 second."""
    try:
        await asyncio.wait_for(ws.close(), timeout=1.0)
    except (asyncio.TimeoutError, Exception):
        pass


class SerialTermServer:
    """Serves the terminal HTML page and relays WebSocket traffic to the serial port."""

    def __init__(
        self,
        server_config: ServerConfig,
        serial_handler: SerialHandler,
    ) -> None:
        self._config = server_config
        self._serial = serial_handler
        self._app = web.Application()
        self._runner: "web.AppRunner | None" = None
        self._active_ws: "set[web.WebSocketResponse]" = set()
        self._clients = ClientManager(grace_period=10.0)
        self._queued_ws: "dict[str, web.WebSocketResponse]" = {}
        self._relay_task: "asyncio.Task | None" = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        web_dir = str(self._config.web_dir)
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/ws", self._handle_websocket)
        self._app.router.add_static("/static/", path=web_dir)

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        socket_path = self._config.unix_socket
        try:
            os.unlink(socket_path)
        except OSError:
            pass
        os.makedirs(os.path.dirname(socket_path), exist_ok=True)
        site = web.UnixSite(self._runner, socket_path)
        await site.start()
        # Fix socket permissions so nginx (kvmd-nginx user, kvmd group) can connect
        os.chmod(socket_path, 0o660)
        logger.info("Server listening on %s (mode 660)", socket_path)

    async def stop(self) -> None:
        if self._relay_task is not None:
            self._relay_task.cancel()
            try:
                await self._relay_task
            except asyncio.CancelledError:
                pass
            self._relay_task = None

        for ws_list in (list(self._active_ws), list(self._queued_ws.values())):
            for ws in ws_list:
                await _close_ws_safe(ws)
        self._active_ws.clear()
        self._queued_ws.clear()

        if self._runner is not None:
            await asyncio.sleep(0.05)
            await self._runner.cleanup()
            self._runner = None
            logger.info("Server stopped")

    async def _handle_index(self, _request: web.Request) -> web.FileResponse:
        return web.FileResponse(
            pathlib.Path(self._config.web_dir) / "index.html"
        )

    # ── Serial relay ──────────────────────────────────────────────────────

    def _is_pty_device(self) -> bool:
        """Check if the configured serial device is a PTY (test fixture)."""
        dev = self._serial._config.device
        return "pts" in dev or dev.startswith("/dev/ttys")

    async def _ensure_serial_dtr_cycle(self) -> None:
        """Close (if open) and reopen serial to cycle DTR, then send
        a newline kick to trigger getty output."""
        if self._serial.is_open:
            if self._is_pty_device():
                logger.info("PTY device, skipping DTR cycle")
                return
            await self._serial.close()
            await asyncio.sleep(0.3)

        await self._serial.open()
        logger.info("Serial port cycled (DTR reset)")
        await asyncio.sleep(0.5)

    async def _start_relay(self, ws: web.WebSocketResponse) -> None:
        if self._relay_task is not None:
            await self._stop_relay()

        await self._ensure_serial_dtr_cycle()

        # CH340 DTR doesn't actually restart agetty on the target machine,
        # so we send a single \n to trigger agetty to re-print the prompt.
        await self._serial.write(b"\n")
        await asyncio.sleep(0.5)

        async def relay() -> None:
            while not ws.closed:
                try:
                    data = await self._serial.read()
                    if data:
                        logger.info("Relay: read %d bytes from serial", len(data))
                        text = data.decode("utf-8", errors="replace")
                        await ws.send_str(text)
                        logger.info("Relay: sent %d bytes to WebSocket", len(data))
                except Exception:
                    logger.exception("Serial read error in relay")
                    break
                await asyncio.sleep(0.01)

        self._relay_task = asyncio.create_task(relay())

    async def _stop_relay(self) -> None:
        if self._relay_task is not None:
            self._relay_task.cancel()
            try:
                await self._relay_task
            except asyncio.CancelledError:
                pass
            self._relay_task = None

    # ── WebSocket handler ─────────────────────────────────────────────────

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Use client-provided session ID for reconnect support
        client_id = request.query.get("sid", "")
        if not client_id:
            # Fallback: generate a random one
            import uuid
            client_id = uuid.uuid4().hex[:12]

        self._active_ws.add(ws)
        logger.info("WebSocket client %s connected", client_id)

        # Try reconnect first, then acquire
        reconnected = self._clients.reconnect(client_id)
        if reconnected:
            await ws.send_str(json.dumps({"type": "active"}))
            await self._start_relay(ws)
            await self._ws_input_loop(ws, client_id)
            return ws

        result = self._clients.acquire(client_id)

        if result["type"] == "active":
            await ws.send_str(json.dumps({"type": "active"}))
            await self._start_relay(ws)
            await self._ws_input_loop(ws, client_id)
        else:
            self._queued_ws[client_id] = ws
            await ws.send_str(json.dumps(result))
            await self._ws_input_loop(ws, client_id)

        return ws

    async def _ws_input_loop(
        self,
        ws: web.WebSocketResponse,
        client_id: str,
    ) -> None:
        was_active = self._clients.is_active(client_id)
        try:
            async for msg in ws:
                may_relay = self._clients.is_active(client_id)
                if msg.type == web.WSMsgType.TEXT:
                    text = msg.data
                    if text.startswith("{"):
                        try:
                            ctrl = json.loads(text)
                            if ctrl.get("type") == "resize":
                                logger.debug(
                                    "Terminal resize: %sx%s (client %s)",
                                    ctrl.get("cols"), ctrl.get("rows"),
                                    client_id,
                                )
                            continue
                        except json.JSONDecodeError:
                            pass
                    if may_relay:
                        await self._serial.write(text.encode("utf-8"))
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error("WebSocket error: %s", ws.exception())
                    break
                elif msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSED):
                    break
        finally:
            self._active_ws.discard(ws)
            if not ws.closed:
                await ws.close()

            if was_active:
                await self._stop_relay()
                promoted = self._clients.release(client_id)
                if promoted:
                    self._promote(promoted)
                elif self._serial.is_open:
                    # Nobody left in queue — end the current getty session
                    # so the next client gets a fresh login banner.
                    logger.info("No queued clients — sending Ctrl+D to close getty session")
                    await self._serial.write(b"\x04")
            else:
                self._queued_ws.pop(client_id, None)
                self._clients.release(client_id)

            logger.info("WebSocket client %s disconnected", client_id)

    def _promote(self, promoted_id: str) -> None:
        ws = self._queued_ws.pop(promoted_id, None)
        if ws is None:
            logger.warning("Promoted client %s not found in queued connections", promoted_id)
            return

        async def promote_and_relay() -> None:
            try:
                await ws.send_str(json.dumps({"type": "active"}))
            except Exception:
                logger.exception("Failed to send promotion notification")
                return
            await self._start_relay(ws)

        asyncio.create_task(promote_and_relay())
