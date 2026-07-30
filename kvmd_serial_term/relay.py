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
        self._task: "asyncio.Task | None" = None
        # True when the active client has typed at least one keystroke.
        # Used to decide whether to Ctrl+D logout the shell on disconnect.
        self.had_activity = False

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
        """Close (if real device), reopen serial, then send \\n to trigger
        getty to re-print the login prompt."""
        if self._serial.is_open:
            if self._is_pty():
                return  # PTY survives close/reopen, skip the cycle
            await self._serial.close()
            await asyncio.sleep(0.3)

        await self._serial.open()
        await asyncio.sleep(0.5)
        await self._serial.write(b"\n")
        await asyncio.sleep(0.5)
        logger.info("Serial kick: port reopened, \\n sent")

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def start(self, ws: web.WebSocketResponse) -> None:
        """Stop the old relay (if any), kick the serial port, then start
        the relay read loop forwarding data to *ws*."""
        if self._task is not None:
            await self.stop()

        self.started.clear()
        self.had_activity = False
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
        self.had_activity = True
        await self._serial.write(data)

    async def logout(self) -> None:
        """Send Ctrl+D to the serial port to end the current getty session."""
        await self.write(b"\x04")
        logger.info("Ctrl+D sent to serial — getty session ended")
