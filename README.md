# PiKVM Serial Terminal

[中文](README.zh.md)

A PiKVM extra that provides interactive command-line access to a target machine via USB-TTL serial adapter through the Web UI — no HDMI display needed.

```
┌─────────────┐     USB-TTL      ┌──────────────────┐
│   PiKVM     │  (CH340+MAX3232) │  Target Machine   │
│             │◄════════════════►│      (Linux)      │
│  Web UI     │   Serial COM     │  Serial Console    │
│   xterm.js  │                  │                    │
└─────────────┘                  └──────────────────┘
```

## Features

- Full xterm.js terminal in the PiKVM Web UI
- Canvas / DOM dual rendering modes
- Auto-detected clickable URLs in terminal output (WebLinks)
- `Ctrl+Shift+F` in-terminal search (Search)
- 10-second reconnect grace period for browser refreshes
- Multi-client queue: first-to-connect gets the port, queued clients auto-promote
- Auto-logout on disconnect — next connection sees a fresh welcome banner
- Configurable serial parameters (baud rate, parity, etc.)
- Standard PiKVM extra deployment: systemd daemon + manifest registration

## Hardware Requirements

- USB-TTL adapter: CH340 (or equivalent) + MAX3232 for RS-232 level shifting
- Target machine with a COM port header on the motherboard

> **Wiring guide: [docs/hardware/wiring.md](docs/hardware/wiring.md) · [中文](docs/hardware/wiring.zh.md)**

## Target Machine Preparation

1. **Enable COM port in BIOS** — usually under "Super IO" or "Peripherals"
2. **Configure a serial console**:

   ```
   # Edit /etc/default/grub
   GRUB_CMDLINE_LINUX="console=ttyS0,115200n8"

   # Apply and reboot
   update-grub
   reboot
   ```

3. **Wire the adapter:**

   See [wiring guide](docs/hardware/wiring.md) · [中文](docs/hardware/wiring.zh.md)

## Installation

On the PiKVM:

```bash
# 1. Clone the repo
git clone https://github.com/pzehrel/kvmd-serial-term.git /opt/kvmd-serial-term
cd /opt/kvmd-serial-term

# 2. Run the deployment script
bash deploy.sh
```

`deploy.sh` handles everything: Python package installation, config file creation, systemd service registration, PiKVM extra registration, and Nginx integration.

## Configuration

`/etc/kvmd/serial-term.yaml`:

> **Finding your serial device:** Plug in the USB-TTL adapter and run
> `ls /dev/ttyUSB*` or `dmesg | grep ttyUSB` on the PiKVM.
> CH340-based adapters usually appear as `/dev/ttyUSB0`.

```yaml
serial:
  device: /dev/ttyUSB0      # Serial device path
  baudrate: 115200          # Baud rate: 300–921600
  bytesize: 8               # Data bits: 5, 6, 7, 8
  parity: N                 # Parity: N, E, O, M, S
  stopbits: 1               # Stop bits: 1, 1.5, 2
  xonxoff: false            # Software flow control
  rtscts: false             # Hardware flow control

server:
  unix_socket: /run/kvmd/serial-term.sock
  web_dir: /usr/share/kvmd/web/serial-term
```

All serial fields are optional — defaults are `115200-8-N-1`.

## Usage

1. Open the PiKVM Web UI
2. Click **Serial Terminal** in the navigation menu (placed before the built-in Terminal)
3. The terminal window opens — log in to the target machine
4. Only one client controls the serial port at a time; others see a full-screen queue notice
5. Closing the page auto-logs out the shell; the next connection shows a fresh welcome banner

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest tests/ -v
```

## License

GPL-3.0
