"""Relay — background task that reads serial data and forwards to a WebSocket.

Each time a new client becomes active, relay.stop() + relay.start(ws) replaces
the old WebSocket target with the new one.  Observable via relay.started.
"""

import asyncio
import logging

from aiohttp import web

from kvmd_serial_term.serial_handler import SerialHandler

logger = logging.getLogger(__name__)


class Relay:
    """Manages the serial→WebSocket relay loop and serial kick lifecycle."""

    def __init__(self, serial: SerialHandler) -> None:
        self._serial = serial
        self.started = asyncio.Event()
        self._task: asyncio.Task | None = None
        # True when the previous client was logged out via Ctrl+D.
        # The next kick can skip the \n because getty restarted itself.
        self._fresh_getty = False

    # ── observable state ──────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    # ── PTY detection (internal) ──────────────────────────────────────────

    def _is_pty(self) -> bool:
        """True when the serial device is a PTY (used in tests)."""
        dev = self._serial.device
        return "pts" in dev or dev.startswith("/dev/ttys")

    # ── serial kick ───────────────────────────────────────────────────────

    async def _kick(self) -> None:
        """Close (if real device), reopen serial.  If the previous client
        was logged out, getty has already restarted and printed the banner;
        just wait.  Otherwise send \\n to trigger getty output."""
        if self._serial.is_open:
            if self._is_pty():
                return
            await self._serial.close()
            await asyncio.sleep(0.3)

        await self._serial.open()

        if self._fresh_getty:
            # Ctrl+D already restarted getty — banner + prompt are coming
            await asyncio.sleep(1.0)
            logger.info("Serial kick: port reopened, waiting for fresh getty banner")
        else:
            # No recent logout — need to trigger getty output
            await asyncio.sleep(0.5)
            await self._serial.write(b"\n")
            await asyncio.sleep(0.5)
            logger.info("Serial kick: \\n sent to trigger login prompt")
        logger.info("Serial kick: port reopened, \\n sent")

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def start(self, ws: web.WebSocketResponse) -> None:
        """Stop the old relay (if any), kick the serial port, then start
        the relay read loop forwarding data to *ws*."""
        if self._task is not None:
            await self.stop()

        self.started.clear()
        await self._kick()

        async def _loop() -> None:
            while not ws.closed:
                try:
                    data = await self._serial.read()
                    if data:
                        text = data.decode("utf-8", errors="replace")
                        await ws.send_str(text)
                except Exception:
                    logger.exception("Relay read error")
                    break
                await asyncio.sleep(0.01)

        self._task = asyncio.create_task(_loop())
        self.started.set()
        logger.info("Relay started")

    async def stop(self) -> None:
        """Cancel the relay loop task.  Safe to call when already stopped."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("Relay stopped")

    async def write(self, data: bytes) -> None:
        """Write raw bytes to the serial port. Used for keystroke forwarding."""
        await self._serial.write(data)

    async def logout(self) -> None:
        """Send Ctrl+D to end the current getty session.  The next kick
        will skip \\n because getty restarts and prints the banner itself."""
        await self.write(b"\x04")
        self._fresh_getty = True
        logger.info("Ctrl+D sent — getty session ended")
