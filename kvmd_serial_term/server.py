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
from kvmd_serial_term.relay import Relay

logger = logging.getLogger(__name__)


async def _close_ws_safe(ws: web.WebSocketResponse) -> None:
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
        self._relay = Relay(serial_handler)
        self._app = web.Application()
        self._runner: "web.AppRunner | None" = None
        self._active_ws: "set[web.WebSocketResponse]" = set()
        self._clients = ClientManager(grace_period=10.0)
        self._queued_ws: "dict[str, web.WebSocketResponse]" = {}
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
        os.chmod(socket_path, 0o660)
        logger.info("Server listening on %s (mode 660)", socket_path)

    async def stop(self) -> None:
        await self._relay.stop()

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

    # ── WebSocket handler ─────────────────────────────────────────────────

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        client_id = request.query.get("sid", "")
        if not client_id:
            import uuid
            client_id = uuid.uuid4().hex[:12]

        self._active_ws.add(ws)
        logger.info("WebSocket client %s connected", client_id)

        # Try reconnect first, then acquire
        reconnected = self._clients.reconnect(client_id)
        if reconnected:
            await ws.send_str(json.dumps({"type": "active"}))
            await self._relay.start(ws)
            await self._ws_input_loop(ws, client_id)
            return ws

        result = self._clients.acquire(client_id)

        if result["type"] == "active":
            await ws.send_str(json.dumps({"type": "active"}))
            await self._relay.start(ws)
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
                        await self._relay.write(text.encode("utf-8"))
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
                await self._relay.stop()
                promoted = self._clients.release(client_id)
                if promoted:
                    self._promote(promoted)
                elif self._relay.had_activity:
                    # User typed something — there's a live shell session. End it.
                    await self._relay.logout()
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
            await self._relay.start(ws)

        asyncio.create_task(promote_and_relay())
