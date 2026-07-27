#!/bin/bash
# PiKVM Serial Terminal — one-shot deployment script
# Run on your PiKVM:
#   curl -fsSL https://raw.githubusercontent.com/pzehrel/kvmd-serial-term/main/deploy.sh | bash
# Or manually:
#   git clone https://github.com/pzehrel/kvmd-serial-term.git /tmp/kvmd-serial-term
#   cd /tmp/kvmd-serial-term && bash deploy.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "==> Deploying from $REPO_DIR"

# ── 0. Remount root as read-write ────────────────────────────────────────
echo "==> Ensuring root is writable..."
mount -o remount,rw / 2>/dev/null || true

# ── 1. Copy Python package to site-packages ──────────────────────────────
PY_SITE=$(python3 -c 'import site; print(site.getsitepackages()[0])')
echo "==> Copying Python package to $PY_SITE..."
cp -r "$REPO_DIR/kvmd_serial_term" "$PY_SITE/"
echo "    Done."

# ── 2. Configuration ────────────────────────────────────────────────────
echo "==> Setting up config..."
if [ ! -f /etc/kvmd/serial-term.yaml ]; then
    mkdir -p /etc/kvmd
    cat > /etc/kvmd/serial-term.yaml <<'EOF'
serial:
  device: /dev/ttyUSB0
  baudrate: 115200
server:
  unix_socket: /run/kvmd/serial-term.sock
  web_dir: /usr/share/kvmd/web/serial-term
EOF
    chown kvmd:kvmd /etc/kvmd/serial-term.yaml
    chmod 644 /etc/kvmd/serial-term.yaml
    echo "    Created /etc/kvmd/serial-term.yaml"
fi

# ── 3. Systemd service ──────────────────────────────────────────────────
echo "==> Installing systemd service..."
# Patch: PiKVM uses 'uucp' group, not 'dialout'
sed 's/SupplementaryGroups=dialout uucp/SupplementaryGroups=uucp/' \
    "$REPO_DIR/kvmd-serial-term.service" > /etc/systemd/system/kvmd-serial-term.service
systemctl daemon-reload
systemctl enable kvmd-serial-term

# ── 4. PiKVM extra (manifest must be INSIDE subdirectory) ───────────────
echo "==> Installing PiKVM extra..."
mkdir -p /usr/share/kvmd/extras/serial-term
cp "$REPO_DIR/manifest.yaml" /usr/share/kvmd/extras/serial-term/manifest.yaml

# ── 5. Nginx config (via PiKVM extras mechanism) ────────────────────────
echo "==> Installing Nginx config..."
cp "$REPO_DIR/nginx.conf.example" /usr/share/kvmd/extras/serial-term/nginx.ctx-server.conf

# ── 6. Web assets ───────────────────────────────────────────────────────
echo "==> Installing web assets..."
mkdir -p /usr/share/kvmd/web/serial-term
cp "$REPO_DIR/web/index.html" /usr/share/kvmd/web/serial-term/
cp "$REPO_DIR/web/xterm.js" /usr/share/kvmd/web/serial-term/
cp "$REPO_DIR/web/xterm.css" /usr/share/kvmd/web/serial-term/
cp "$REPO_DIR/web/xterm-addon-fit.js" /usr/share/kvmd/web/serial-term/

# ── 7. SVG icon ─────────────────────────────────────────────────────────
cp "$REPO_DIR/web/serial.svg" /usr/share/kvmd/web/share/svg/serial.svg

# ── 8. Serial device permissions ────────────────────────────────────────
echo "==> Checking serial device..."
usermod -a -G uucp kvmd 2>/dev/null || true
if [ -e /dev/ttyUSB0 ]; then
    echo "    /dev/ttyUSB0 found"
else
    echo "    WARNING: /dev/ttyUSB0 not found — plug in the USB-TTL adapter"
fi

# ── 9. Restart services ─────────────────────────────────────────────────
echo "==> Restarting services..."
systemctl restart kvmd-nginx 2>/dev/null || true
systemctl restart kvmd-serial-term 2>/dev/null || true
systemctl restart kvmd 2>/dev/null || true
sleep 2

echo ""
echo "============================================"
echo "  Deployment complete!"
echo ""
echo "  Verify:"
echo "    systemctl status kvmd-serial-term"
echo "    journalctl -u kvmd-serial-term -f"
echo "    curl -sk https://localhost/serial/"
echo ""
echo "  Open the PiKVM Web UI — 'Serial Terminal'"
echo "  should appear in the navigation menu."
echo "============================================"
