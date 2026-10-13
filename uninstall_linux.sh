#!/usr/bin/env bash
# Remove what install_linux.sh created: app launcher, icon, venv and the
# headless systemd user service. Leaves the checkout and config.json alone.
set -euo pipefail

VENV_DIR="${TWITCHTTS_VENV:-$HOME/.local/share/twitchtts/venv}"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
UNIT="$HOME/.config/systemd/user/twitchtts.service"

if [ -f "$UNIT" ]; then
    echo "==> Removing systemd user service"
    systemctl --user disable --now twitchtts 2>/dev/null || true
    rm -f "$UNIT"
    systemctl --user daemon-reload 2>/dev/null || true
fi

echo "==> Removing app launcher and icon"
rm -f "$DATA_DIR/applications/twitchtts.desktop" \
      "$DATA_DIR/icons/hicolor/scalable/apps/twitchtts.svg"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_DIR/applications" >/dev/null 2>&1 || true

echo "==> Removing virtualenv $VENV_DIR"
rm -rf "$VENV_DIR"
rmdir "$(dirname "$VENV_DIR")" 2>/dev/null || true

echo "==> Done. Your config.json and this folder were left in place."
