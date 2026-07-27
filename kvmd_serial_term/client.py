"""Client management — exclusive serial port access with queue and grace period."""

import logging
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ClientManager:
    """Manages exclusive access to the serial port.

    - First client to call acquire() gets the port.
    - Subsequent clients enter a FIFO queue.
    - When the active client releases, the next queued client is promoted.
    - A client that releases can reconnect within a grace period.
    """

    def __init__(self, grace_period: float = 10.0) -> None:
        self._grace_period = grace_period
        self._active: Optional[str] = None
        self._queue: list[str] = []
        # Map: client_id → timestamp of last release (for grace period)
        self._grace: Dict[str, float] = {}

    # ── public API ────────────────────────────────────────────────────────

    def acquire(self, client_id: str) -> dict:
        """Request access to the serial port.

        Returns:
            {"type": "active"} if the client gets the port.
            {"type": "queue", "position": N} if the client is placed in the queue.
        """
        if self._active == client_id:
            return {"type": "active"}

        if client_id in self._queue:
            pos = self._queue.index(client_id) + 1  # 1-indexed
            return {"type": "queue", "position": pos}

        if self._active is None:
            self._active = client_id
            self._grace.pop(client_id, None)  # Clear grace entry on re-acquire
            logger.info("Client %s acquired serial port", client_id)
            return {"type": "active"}

        self._queue.append(client_id)
        pos = len(self._queue)  # 1-indexed: first queued = position 1
        logger.info("Client %s queued at position %s", client_id, pos)
        return {"type": "queue", "position": pos}

    def release(self, client_id: str) -> Optional[str]:
        """Release the serial port.

        If client_id is the active holder, the next queued client is promoted.

        Returns:
            The promoted client_id, or None if nobody was promoted.
        """
        if client_id == self._active:
            self._active = None
            self._grace[client_id] = time.monotonic()
            logger.info("Client %s released serial port", client_id)
            return self._promote_next()

        if client_id in self._queue:
            self._queue.remove(client_id)
            logger.info("Client %s left the queue", client_id)
            return None

        return None

    def reconnect(self, client_id: str) -> bool:
        """Attempt to reconnect within the grace period.

        Only works for a client that previously held the port and released it.

        Returns:
            True if the client was reconnected as active.
        """
        if client_id not in self._grace:
            return False

        elapsed = time.monotonic() - self._grace[client_id]
        if elapsed > self._grace_period:
            del self._grace[client_id]
            return False

        if self._active is not None and self._active != client_id:
            return False  # Someone else has the port now

        self._active = client_id
        del self._grace[client_id]
        logger.info("Client %s reconnected within grace period", client_id)
        return True

    def is_active(self, client_id: str) -> bool:
        """Check if client_id currently holds the serial port."""
        return self._active == client_id

    def get_position(self, client_id: str) -> Optional[int]:
        """Return the 1-indexed queue position, or None if not queued."""
        if client_id in self._queue:
            return self._queue.index(client_id) + 1
        return None

    # ── internals ─────────────────────────────────────────────────────────

    def _promote_next(self) -> Optional[str]:
        """Promote the next client in the queue to active."""
        if not self._queue:
            return None
        promoted = self._queue.pop(0)
        self._active = promoted
        self._grace.pop(promoted, None)  # Clear grace entry
        logger.info("Client %s promoted from queue", promoted)
        return promoted
