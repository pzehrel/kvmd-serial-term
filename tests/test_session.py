"""Tests for serial port session management — exclusive access, queue, grace period."""

import asyncio

import pytest

from kvmd_serial_term.session import SessionManager


@pytest.mark.asyncio
async def test_first_client_acquires():
    """The first client to call acquire() gets the port immediately."""
    mgr = SessionManager(grace_period=10.0)

    result = mgr.acquire("client-1")
    assert result["type"] == "active"


@pytest.mark.asyncio
async def test_second_client_queued():
    """A second client is placed in the queue with position 1."""
    mgr = SessionManager(grace_period=10.0)

    mgr.acquire("client-1")
    result = mgr.acquire("client-2")
    assert result["type"] == "queue"
    assert result["position"] == 1


@pytest.mark.asyncio
async def test_third_client_queued_position_2():
    """A third client is queued behind the second."""
    mgr = SessionManager(grace_period=10.0)

    mgr.acquire("client-1")
    mgr.acquire("client-2")
    result = mgr.acquire("client-3")
    assert result["type"] == "queue"
    assert result["position"] == 2


@pytest.mark.asyncio
async def test_release_promotes_next():
    """When the active client releases, the next queued client is promoted."""
    mgr = SessionManager(grace_period=10.0)

    mgr.acquire("client-1")
    mgr.acquire("client-2")

    promoted = mgr.release("client-1")
    assert promoted == "client-2"


@pytest.mark.asyncio
async def test_queue_positions_update_after_promotion():
    """After promotion, remaining queued clients' positions shift down."""
    mgr = SessionManager(grace_period=10.0)

    mgr.acquire("client-1")  # active
    mgr.acquire("client-2")  # position 1
    result3 = mgr.acquire("client-3")  # position 2

    # Release active — client-2 promoted, client-3 moves to position 1
    mgr.release("client-1")

    # client-3 should now have position 1 (query by calling acquire again...
    # but acquire would return "already queued" — let me check)
    # Actually, re-acquire for the same client: no, that's for reconnect
    pos = mgr.get_position("client-3")
    assert pos == 1


@pytest.mark.asyncio
async def test_release_nonexistent_returns_none():
    """Releasing a client that isn't active or queued returns None."""
    mgr = SessionManager(grace_period=10.0)
    assert mgr.release("nobody") is None


@pytest.mark.asyncio
async def test_release_queued_client_removes_from_queue():
    """Releasing a queued (non-active) client removes it without promotion."""
    mgr = SessionManager(grace_period=10.0)

    mgr.acquire("client-1")  # active
    mgr.acquire("client-2")  # queued

    mgr.release("client-2")  # client-2 leaves the queue

    # Release active: nobody to promote
    promoted = mgr.release("client-1")
    assert promoted is None


@pytest.mark.asyncio
async def test_grace_period_reconnect():
    """A client that disconnects can reconnect within the grace period."""
    mgr = SessionManager(grace_period=10.0)

    mgr.acquire("client-1")
    mgr.release("client-1")

    reconnected = mgr.reconnect("client-1")
    assert reconnected is True
    assert mgr.is_active("client-1")


@pytest.mark.asyncio
async def test_grace_period_expired():
    """After the grace period expires, reconnect is rejected."""
    mgr = SessionManager(grace_period=0.01)

    mgr.acquire("client-1")
    mgr.release("client-1")

    await asyncio.sleep(0.05)  # Grace period expired

    reconnected = mgr.reconnect("client-1")
    assert reconnected is False


@pytest.mark.asyncio
async def test_reconnect_same_client_only():
    """Only the client that previously held the port can reconnect."""
    mgr = SessionManager(grace_period=10.0)

    mgr.acquire("client-1")
    mgr.release("client-1")

    # client-2 never held the port, shouldn't be able to reconnect
    reconnected = mgr.reconnect("client-2")
    assert reconnected is False


@pytest.mark.asyncio
async def test_is_active():
    """is_active returns True only for the client holding the port."""
    mgr = SessionManager(grace_period=10.0)

    mgr.acquire("client-1")
    mgr.acquire("client-2")

    assert mgr.is_active("client-1") is True
    assert mgr.is_active("client-2") is False
    assert mgr.is_active("nobody") is False


@pytest.mark.asyncio
async def test_acquire_while_queued_returns_queue_position():
    """Calling acquire again for an already-queued client returns its current position."""
    mgr = SessionManager(grace_period=10.0)

    mgr.acquire("client-1")
    mgr.acquire("client-2")

    # client-2 calls acquire again (e.g. reconnecting while queued)
    result = mgr.acquire("client-2")
    assert result["type"] == "queue"
    assert result["position"] == 1
