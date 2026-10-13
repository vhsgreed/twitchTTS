#!/usr/bin/env bash
# Install the Twitch TTS Engine on Linux.
#   - Desktop: runs the full tray app (needs a display).
#   - Headless server: installs a systemd user service for the engine only;
#     audio plays in the browser UI (http://localhost:8080/index.html).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${TWITCHTTS_VENV:-$HOME/.local/share/twitchtts/venv}"

# python3-venv is a hard prereq on Debian/Ubuntu (ensurepip lives there).
if command -v apt-get >/dev/null 2>&1 && ! python3 -c "import ensurepip" 2>/dev/null; then
    echo "==> Installing python3-venv (required to create the virtualenv)"
    sudo apt-get install -y python3-venv >/dev/null 2>&1 || {
        echo "    Install it manually: sudo apt-get install python3-venv"
        exit 1
    }
fi

# systemctl --user needs these in non-login SSH shells (headless installs).
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

echo "==> Creating virtualenv at $VENV_DIR"
# --system-site-packages: the tray menu needs PyGObject (python3-gi, a system
# package) for pystray's GTK backend; without it pystray falls back to xorg,
# which has no right-click menu.
python3 -m venv --system-site-packages "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements-linux.txt"

# Tray menu: PyGObject + GTK3 (system packages, not pip-installable).
if command -v apt-get >/dev/null 2>&1 && ! python3 -c "import gi; gi.require_version('Gtk','3.0')" 2>/dev/null; then
    echo "==> Installing python3-gi + gir1.2-gtk-3.0 (needed for the tray menu)"
    if sudo -n true 2>/dev/null; then
        sudo apt-get install -y python3-gi gir1.2-gtk-3.0 >/dev/null 2>&1 || echo "    (could not install; tray will have no menu)"
    else
        echo "    sudo not available passwordlessly - install manually: sudo apt-get install python3-gi gir1.2-gtk-3.0"
    fi
fi

# The tray window needs Tk; it is a system package (not pip-installable).
if command -v apt-get >/dev/null 2>&1 && ! python3 -c "import tkinter" 2>/dev/null; then
    echo "==> Installing python3-tk (needed for the tray window)"
    if sudo -n true 2>/dev/null; then
        sudo apt-get install -y python3-tk >/dev/null 2>&1 || echo "    (could not install python3-tk; tray GUI needs it)"
    else
        echo "    sudo not available passwordlessly - install manually: sudo apt-get install python3-tk"
    fi
fi

if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    # App menu launcher: shows in the app grid, can be pinned to the dock,
    # and the window groups under it (StartupWMClass = Tk className).
    DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
    ICON_DIR="$DATA_DIR/icons/hicolor/scalable/apps"
    APP_DIR="$DATA_DIR/applications"
    mkdir -p "$ICON_DIR" "$APP_DIR"
    install -m 644 "$REPO_DIR/assets/twitchtts.svg" "$ICON_DIR/twitchtts.svg"
    cat > "$APP_DIR/twitchtts.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Twitch TTS
GenericName=Chat text-to-speech
Comment=Read Twitch chat aloud
Exec=$VENV_DIR/bin/python $REPO_DIR/twitchtts_app.py
Path=$REPO_DIR
Icon=twitchtts
Terminal=false
Categories=AudioVideo;Audio;
Keywords=twitch;tts;chat;stream;
StartupWMClass=Twitchtts
Actions=open;mute;about;exit;

[Desktop Action open]
Name=Open
Exec=$VENV_DIR/bin/python $REPO_DIR/twitchtts_app.py --open

[Desktop Action mute]
Name=Mute / Unmute
Exec=$VENV_DIR/bin/python $REPO_DIR/twitchtts_app.py --mute

[Desktop Action about]
Name=About
Exec=$VENV_DIR/bin/python $REPO_DIR/twitchtts_app.py --about

[Desktop Action exit]
Name=Exit
Exec=$VENV_DIR/bin/python $REPO_DIR/twitchtts_app.py --exit
EOF
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$DATA_DIR/icons/hicolor" >/dev/null 2>&1 || true
    echo "==> Installed. Open \"Twitch TTS\" from your app menu (right-click it to pin it to the dock)."
    echo "    Terminal launch still works: $VENV_DIR/bin/python $REPO_DIR/twitchtts_app.py"
    echo "    Re-run this script after moving the checkout. Remove with ./uninstall_linux.sh"
else
    SERVICE_NAME="twitchtts"
    UNIT="$HOME/.config/systemd/user/$SERVICE_NAME.service"
    mkdir -p "$(dirname "$UNIT")"
    cat > "$UNIT" <<EOF
[Unit]
Description=Twitch TTS Engine (headless)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
ExecStart=$VENV_DIR/bin/python $REPO_DIR/app.py
Restart=on-failure
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now "$SERVICE_NAME"
    echo "==> Headless service installed. Config: $REPO_DIR/config.json"
    echo "    Edit it, then: systemctl --user restart $SERVICE_NAME"
    echo "    Keep it running after logout: loginctl enable-linger \$(id -u)"
    systemctl --user status "$SERVICE_NAME" --no-pager | head -n 8
fi
