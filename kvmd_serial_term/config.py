"""Configuration loading and validation for kvmd-serial-term."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import TextIO

import yaml

# ── defaults ─────────────────────────────────────────────────────────────────

DEFAULT_SERIAL_CONFIG = {
    "device": "/dev/ttyUSB0",
    "baudrate": 115200,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "xonxoff": False,
    "rtscts": False,
}

DEFAULT_SERVER_CONFIG = {
    "unix_socket": "/run/kvmd-serial-term.sock",
    # Default: repo-local web/ for dev; override on PiKVM
    "web_dir": str(pathlib.Path(__file__).resolve().parent.parent / "web"),
}

DEFAULT_CONFIG_PATH = "/etc/kvmd/serial-term.yaml"


# ── dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class SerialConfig:
    """Serial port configuration with sensible defaults."""

    device: str = DEFAULT_SERIAL_CONFIG["device"]
    baudrate: int = DEFAULT_SERIAL_CONFIG["baudrate"]
    bytesize: int = DEFAULT_SERIAL_CONFIG["bytesize"]
    parity: str = DEFAULT_SERIAL_CONFIG["parity"]
    stopbits: int = DEFAULT_SERIAL_CONFIG["stopbits"]
    xonxoff: bool = DEFAULT_SERIAL_CONFIG["xonxoff"]
    rtscts: bool = DEFAULT_SERIAL_CONFIG["rtscts"]


@dataclass
class ServerConfig:
    """Server configuration."""

    unix_socket: str = DEFAULT_SERVER_CONFIG["unix_socket"]
    web_dir: str = DEFAULT_SERVER_CONFIG["web_dir"]


@dataclass
class AppConfig:
    """Top-level application configuration."""

    serial: SerialConfig = field(default_factory=SerialConfig)
    server: ServerConfig = field(default_factory=ServerConfig)


# ── loader ───────────────────────────────────────────────────────────────────

def _merge(raw: dict | None, defaults: dict, factory: type):
    """Merge raw YAML block with defaults, return a dataclass instance."""
    if raw is None:
        raw = {}
    kwargs = {k: raw.get(k, v) for k, v in defaults.items()}
    return factory(**kwargs)


def load_config(source: str | TextIO, _path_hint: str | None = None) -> AppConfig:
    """Load configuration from a YAML file path or a file-like object.

    Args:
        source: Either a file path (str) or an open file-like object.
        _path_hint: Original path for diagnostics (used internally when
                    source is already a file object).

    Returns:
        An AppConfig with all fields populated — missing keys get defaults.
    """
    if isinstance(source, str):
        with open(source, "r") as fh:
            raw = yaml.safe_load(fh) or {}
    else:
        raw = yaml.safe_load(source) or {}

    return AppConfig(
        serial=_merge(raw.get("serial"), DEFAULT_SERIAL_CONFIG, SerialConfig),
        server=_merge(raw.get("server"), DEFAULT_SERVER_CONFIG, ServerConfig),
    )
