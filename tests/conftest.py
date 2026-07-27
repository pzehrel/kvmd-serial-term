"""Shared test fixtures and helpers."""

import os
import pty


def make_pty_pair():
    """Create a PTY pair and return (master_fd, slave_name).

    The handler opens `slave_name` as its "serial device".
    The test reads/writes to `master_fd` as the "remote computer".
    """
    master_fd, slave_fd = pty.openpty()
    slave_name = os.ttyname(slave_fd)
    os.close(slave_fd)
    return master_fd, slave_name
