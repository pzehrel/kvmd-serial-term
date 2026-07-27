#!/bin/bash
# PiKVM Serial Terminal — one-shot deployment script
# Run this on your PiKVM device:
#   curl -fsSL https://raw.githubusercontent.com/pzehrel/kvmd-serial-term/main/deploy.sh | bash
#
# Or manually after cloning:
#   git clone https://github.com/pzehrel/kvmd-serial-term.git /tmp/kvmd-serial-term
#   cd /tmp/kvmd-serial-term && bash deploy.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "==> Deploying from $REPO_DIR"

# ── 1. Install Python package ───────────────────────────────────────────
echo "==> Installing Python package..."
cd "$REPO_DIR"
pip install -e . 2>/dev/null || pip install .

# ── 2. Configuration ────────────────────────────────────────────────────
echo "==> Setting up config..."
if [ ! -f /etc/kvmd/serial-term.yaml ]; then
    mkdir -p /etc/kvmd
    cat > /etc/kvmd/serial-term.yaml <<'EOF'
serial:
  device: /dev/ttyUSB0
  baudrate: 115200
server:
  unix_socket: /run/kvmd-serial-term.sock
  web_dir: /usr/share/kvmd/web/serial-term
EOF
    chown kvmd:kvmd /etc/kvmd/serial-term.yaml
    chmod 644 /etc/kvmd/serial-term.yaml
    echo "    Created /etc/kvmd/serial-term.yaml (edit if using a different device)"
fi

# ── 3. Systemd service ──────────────────────────────────────────────────
echo "==> Installing systemd service..."
cp "$REPO_DIR/kvmd-serial-term.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable kvmd-serial-term

# ── 4. PiKVM extra manifest ─────────────────────────────────────────────
echo "==> Installing PiKVM extra manifest..."
mkdir -p /usr/share/kvmd/extras
cp "$REPO_DIR/manifest.yaml" /usr/share/kvmd/extras/serial-term.yaml

# ── 5. Web assets ───────────────────────────────────────────────────────
echo "==> Installing web assets..."
mkdir -p /usr/share/kvmd/web/serial-term
cp "$REPO_DIR/web/index.html" /usr/share/kvmd/web/serial-term/
cp "$REPO_DIR/web/xterm.js" /usr/share/kvmd/web/serial-term/
cp "$REPO_DIR/web/xterm.css" /usr/share/kvmd/web/serial-term/
cp "$REPO_DIR/web/xterm-addon-fit.js" /usr/share/kvmd/web/serial-term/

# ── 6. SVG icon ─────────────────────────────────────────────────────────
cp "$REPO_DIR/web/serial.svg" /usr/share/kvmd/web/share/svg/serial.svg

# ── 7. Nginx integration ────────────────────────────────────────────────
echo "==> Configuring Nginx..."
NGINX_CONF="/etc/kvmd/nginx/serial-term.conf"
if [ ! -f "$NGINX_CONF" ]; then
    cat > "$NGINX_CONF" <<'NGINX'
# Serial Terminal — proxy to kvmd-serial-term daemon via Unix socket

location /serial/ {
    proxy_pass http://unix:/run/kvmd-serial-term.sock:/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
}
NGINX
    echo "    Created $NGINX_CONF"
fi

# Include the conf in the main nginx config if not already there
MAIN_NGINX="/etc/kvmd/nginx/nginx.conf.mako"
if ! grep -q "serial-term.conf" "$MAIN_NGINX" 2>/dev/null; then
    echo '    include kvmd/nginx/serial-term.conf;' >> "$MAIN_NGINX"
    echo "    Added include to $MAIN_NGINX"
fi

echo "==> Restarting kvmd-nginx..."
systemctl restart kvmd-nginx || echo "    (kvmd-nginx restart skipped — start manually after verifying config)"

# ── 8. Serial device permissions ────────────────────────────────────────
echo "==> Checking serial device..."
if [ -e /dev/ttyUSB0 ]; then
    echo "    /dev/ttyUSB0 found"
    # Ensure kvmd user can access it
    usermod -a -G dialout kvmd 2>/dev/null || true
else
    echo "    WARNING: /dev/ttyUSB0 not found — plug in the USB-TTL adapter first"
    echo "    Then run: systemctl restart kvmd-serial-term"
fi

# ── 9. Start the service ────────────────────────────────────────────────
echo "==> Starting kvmd-serial-term..."
systemctl restart kvmd-serial-term
sleep 2
systemctl status kvmd-serial-term --no-pager || true

echo ""
echo "============================================"
echo "  Deployment complete!"
echo ""
echo "  Verify:"
echo "    systemctl status kvmd-serial-term"
echo "    journalctl -u kvmd-serial-term -f"
echo "    curl -s http://localhost/serial/"
echo ""
echo "  Then open the PiKVM Web UI — 'Serial Terminal'"
echo "  should appear in the navigation menu."
echo "============================================"
