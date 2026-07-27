# PiKVM Serial Console

A PiKVM extension that lets you control a target machine via a USB-TTL serial adapter through the PiKVM Web UI — no HDMI display needed.

```
┌─────────────┐     USB-TTL      ┌──────────────────┐
│   PiKVM     │  (CH340+MAX3232) │   Target Machine  │
│             │◄════════════════►│   (e.g. Proxmox)  │
│  Web UI     │   Serial COM     │   Serial Console  │
│   xterm.js  │                  │                   │
└─────────────┘                  └──────────────────┘
```

## Features

- Full terminal experience (xterm.js) in the PiKVM Web UI
- Persists across browser refreshes (10s grace period for reconnection)
- Multiple clients queue gracefully — first to connect gets the port
- Configurable serial parameters (baud rate, parity, etc.)
- Runs as a standard PiKVM "extra" with systemd supervision

## Hardware Requirements

- USB-TTL adapter: CH340 (or similar) + MAX3232 for RS-232 level shifting
- Target machine with a COM port header on the motherboard

## Target Machine Preparation

1. **Enable COM port in BIOS** — usually enabled by default, check the "Super IO" or "Peripherals" section
2. **Configure serial console** for your OS:

   **Proxmox VE / Debian / Ubuntu:**
   ```
   # Edit /etc/default/grub
   GRUB_CMDLINE_LINUX="console=ttyS0,115200n8"

   # Apply and reboot
   update-grub
   reboot
   ```

   **Generic Linux:**
   Add `console=ttyS0,115200n8` to your kernel command line

3. **Wire the adapter:**
   | USB-TTL Pin | Target COM Header |
   |-------------|------------------|
   | TX          | RX               |
   | RX          | TX               |
   | GND         | GND              |

## Installation

On the PiKVM device:

```bash
# 1. Clone the repo
git clone https://github.com/pzehrel/kvmd-serial-term.git /opt/kvmd-serial-term
cd /opt/kvmd-serial-term

# 2. Install the Python package
pip install -e .

# 3. Create default config
mkdir -p /etc/kvmd
cat > /etc/kvmd/serial-term.yaml <<EOF
serial:
  device: /dev/ttyUSB0
  baudrate: 115200
EOF

# 4. Install systemd service
cp kvmd-serial-term.service /usr/lib/systemd/system/
systemctl daemon-reload
systemctl enable --now kvmd-serial-term

# 5. Install PiKVM extra manifest
cp manifest.yaml /etc/kvmd/extras/serial-term.yaml
cp web/serial.svg /usr/share/kvmd/web/share/svg/serial.svg

# 6. Add Nginx config (see nginx.conf.example)
# Merge the location blocks into your PiKVM Nginx config
# then: systemctl restart kvmd-nginx
```

## Configuration

`/etc/kvmd/serial-term.yaml`:

```yaml
serial:
  device: /dev/ttyUSB0      # Serial device path
  baudrate: 115200          # 300–921600
  bytesize: 8               # 5, 6, 7, 8
  parity: N                 # N, E, O, M, S
  stopbits: 1               # 1, 1.5, 2
  xonxoff: false            # Software flow control
  rtscts: false             # Hardware flow control

server:
  unix_socket: /run/kvmd-serial-term.sock
```

All serial fields are optional — defaults are `115200-8-N-1`.

## Usage

1. Open the PiKVM Web UI
2. Click **Serial Console** in the navigation menu
3. A terminal window opens — start typing commands
4. Only one client at a time controls the serial port; additional clients wait in a queue

## Development

```bash
# Create venv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## License

GPL-3.0
