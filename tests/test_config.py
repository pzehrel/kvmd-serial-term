"""Tests for configuration loading and validation."""

import io
import os
import tempfile

from kvmd_serial_term.config import (
    DEFAULT_SERIAL_CONFIG,
    DEFAULT_SERVER_CONFIG,
    SerialConfig,
    ServerConfig,
    load_config,
)


def test_default_serial_config():
    """Default serial config matches 115200-8-N-1."""
    cfg = SerialConfig()
    assert cfg.device == "/dev/ttyUSB0"
    assert cfg.baudrate == 115200
    assert cfg.bytesize == 8
    assert cfg.parity == "N"
    assert cfg.stopbits == 1
    assert cfg.xonxoff is False
    assert cfg.rtscts is False


def test_default_server_config():
    """Default server config has expected Unix socket path."""
    cfg = ServerConfig()
    assert cfg.unix_socket == "/run/kvmd-serial-term.sock"


def test_load_config_minimal_yaml():
    """A minimal config with just the device path should work — all other fields get defaults."""
    yaml_text = """
serial:
  device: /dev/ttyUSB2
"""
    cfg = load_config(io.StringIO(yaml_text))
    assert cfg.serial.device == "/dev/ttyUSB2"
    # All other fields should be defaults
    assert cfg.serial.baudrate == DEFAULT_SERIAL_CONFIG["baudrate"]
    assert cfg.serial.bytesize == DEFAULT_SERIAL_CONFIG["bytesize"]
    assert cfg.serial.parity == DEFAULT_SERIAL_CONFIG["parity"]
    assert cfg.serial.stopbits == DEFAULT_SERIAL_CONFIG["stopbits"]
    assert cfg.serial.xonxoff == DEFAULT_SERIAL_CONFIG["xonxoff"]
    assert cfg.serial.rtscts == DEFAULT_SERIAL_CONFIG["rtscts"]
    # Server defaults
    assert cfg.server.unix_socket == DEFAULT_SERVER_CONFIG["unix_socket"]


def test_load_config_full_yaml():
    """All serial fields can be overridden."""
    yaml_text = """
serial:
  device: /dev/ttyUSB1
  baudrate: 9600
  bytesize: 7
  parity: E
  stopbits: 2
  xonxoff: true
  rtscts: true
server:
  unix_socket: /tmp/custom.sock
"""
    cfg = load_config(io.StringIO(yaml_text))
    assert cfg.serial.device == "/dev/ttyUSB1"
    assert cfg.serial.baudrate == 9600
    assert cfg.serial.bytesize == 7
    assert cfg.serial.parity == "E"
    assert cfg.serial.stopbits == 2
    assert cfg.serial.xonxoff is True
    assert cfg.serial.rtscts is True
    assert cfg.server.unix_socket == "/tmp/custom.sock"


def test_load_config_from_file():
    """Config can be loaded from a file path."""
    yaml_text = """
serial:
  device: /dev/ttyUSB0
  baudrate: 57600
"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(yaml_text)
        f.flush()
        cfg = load_config(f.name)

    assert cfg.serial.device == "/dev/ttyUSB0"
    assert cfg.serial.baudrate == 57600
    os.unlink(f.name)


def test_load_config_missing_device_uses_default():
    """If serial section exists but device is omitted, default is used."""
    yaml_text = """
serial:
  baudrate: 38400
"""
    cfg = load_config(io.StringIO(yaml_text))
    assert cfg.serial.device == DEFAULT_SERIAL_CONFIG["device"]
    assert cfg.serial.baudrate == 38400


def test_load_config_no_serial_section_uses_all_defaults():
    """An empty config file yields all defaults."""
    yaml_text = "---\n"
    cfg = load_config(io.StringIO(yaml_text))
    assert cfg.serial.device == DEFAULT_SERIAL_CONFIG["device"]
    assert cfg.serial.baudrate == DEFAULT_SERIAL_CONFIG["baudrate"]
    assert cfg.server.unix_socket == DEFAULT_SERVER_CONFIG["unix_socket"]
