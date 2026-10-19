# Twitch TTS Engine

Reads Twitch chat aloud. Anonymous IRC connection, no API keys, runs in the
tray, plays through your speakers — made for stream overlays and local
monitoring.

![License: MIT](https://img.shields.io/badge/license-MIT-blue)
![Version](https://img.shields.io/badge/version-0.3.0-green)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-important)

## Features

- **Anonymous Twitch IRC** — no Twitch developer account or tokens needed
- **Three TTS engines** — cloud neural voices via [edge-tts](https://github.com/rany2/edge-tts)
  (default, needs internet), offline neural voices via
  [Piper](https://github.com/OHF-Voice/piper1-gpl) (Windows and Linux), or
  offline Windows SAPI voices; switch live in the app
- **Automatic fallback** — when edge-tts fails (no internet, or Microsoft
  rejecting the client), messages are spoken with Piper instead of dropped
- **Desktop app (Windows, Linux)** — control panel with mute/skip, voice + engine selector,
  volume, now-playing, live log, and an Options page for configuration
- **Minimizable** to tray!
- **Viewer voice command** — `!voice <name>` lets viewers pick their own
  voice, remembered per user across restarts
- **Host audio playback** — bounded queue, skip, live volume/mute
- **Content sanitization** — strips Twitch/BTTV/FFZ/7TV emotes, emojis, and
  URLs before synthesis
- **Config-driven rules** — command prefix, special users, per-user cooldown,
  message length limit
- **Local-only API** — all endpoints reject non-loopback origins

## Quick start

### Standalone exe (recommended)

Download `twitchTTS.exe` from the [latest release](https://github.com/vhsgreed/twitchTTS/releases)
and run it. First launch creates `config.json` in `%APPDATA%\TwitchTTS`;
open the window and use **Options...** to set your channel.

### Linux

Run `./install_linux.sh`, then open **Twitch TTS** from the app menu. See
[Linux / headless server](#linux--headless-server).

### From source

```bash
pip install -r requirements.txt
python twitchtts_app.py
```

Neural voices need `edge-tts>=7.3.1`: Microsoft's speech service rejects
older edge-tts releases with `403 Invalid response status`. A daily
workflow raises this pin when a newer edge-tts passes a synthesis test;
upgrade with `pip install -U edge-tts`.

Or double-click `start_tts.bat` (prefers the project venv). At minimum set
your channel in `config.json` (auto-created from `config.example.json`):

```json
{ "twitch_channel": "your_channel_name" }
```

> **One instance only.** Launching a second copy focuses the already-running
> window instead of starting a second engine. Closing the window minimizes to
> tray by default — use **Exit** from the tray menu to quit.

## The app window

| Control | Function |
|---|---|
| **Mute / Skip** | Mute host audio / skip the current message |
| **Voice** | Select the active voice (neural or system) |
| **Engine** | Switch between Neural (edge-tts, cloud), Piper (offline) and System (SAPI, offline, Windows) |
| **Volume** | Vertical slider; adjusts host playback volume |
| **Now Playing** | Current message + queue depth |
| **Engine Log** | Real-time status |
| **About** | Version, license, third-party software |
| **Options...** | Edit config from the GUI ("Save & Restart" applies immediately) |

## Tray Icon

 - **Left click** maximizes program
 - **Right click** small curtain menu
 - Tray icon changes color to represent different states of operation.

| Icon | Meaning |
|-----|----------|
| 🟢 | Engine is OK (normal operation) |
| 🟡 | Engine starting (API not up or chat not connected yet) |
| 🔴 | Engine error |
| ⚪ | Engine is offline |
| 🔇 |	Muted active |

## Configuration

`config.json` lives next to the sources when running from a checkout, or in
`%APPDATA%\TwitchTTS\config.json` for the exe. Edit it via **Options...**
instead of by hand.

| Key | Default | Description |
|---|---|---|
| `twitch_channel` | `your_channel_name` | Target Twitch channel |
| `http_port` / `stream_port` | `8080` / `8081` | API / SSE stream ports |
| `tts_voice` | `en-US-JennyNeural` | edge-tts voice |
| `tts_mode` | `edge` | `edge` (cloud), `piper` (offline neural) or `system` (offline SAPI, Windows) |
| `tts_fallback` | `true` | When the active engine fails, try the others (edge -> Piper -> SAPI) |
| `piper_voice` | `en_US-joe-medium` | Piper voice; any name from the [voice list](https://huggingface.co/rhasspy/piper-voices) |
| `system_voice` | `""` | Windows SAPI voice; empty = Windows default |
| `piper_auto_download` | `true` | Download the Piper voice (~60 MB) on first run |
| `command_prefix` | `!tts` | Prefix for speech-eligible messages |
| `special_users` | `[]` | Users who speak without prefix and bypass cooldown |
| `cooldown_seconds` | `3` | Per-user cooldown between messages |
| `max_chars` | `200` | Max accepted message length |
| `close_to_tray` | `true` | Close button minimizes to tray |
| `audio.*` | `enabled: true, volume: 0.8, muted: false, queue_size: 50` | Host playback |

## Offline voices (Piper)

Piper runs on the CPU (about 0.15 s for a 100-character message on a
laptop-class CPU) and needs no internet once its voice is downloaded. The
first start downloads `piper_voice` (~60 MB) into `piper-voices/` next to
`config.json`. To change voice, pick a name from the
[voice list](https://huggingface.co/rhasspy/piper-voices) and enter it under
**Options...**: set Engine to Piper, then type the name under Voice; it
downloads on save.

Voices carry their own dataset licenses. The default, `en_US-joe-medium`, is
CC0. Some voices (for example `ryan`, `hfc_*`) are CC BY-NC-SA, i.e. not for
monetized streams; check the voice's `MODEL_CARD` before using it.

## Chat commands

| Command | Who | Effect |
|---|---|---|
| `!tts <text>` | everyone | Speaks `<text>` (prefix configurable) |
| `!voice <name>` | everyone | Sets your personal voice |
| `!voice` | everyone | Reports your current voice |
| `!voice reset` | everyone | Clears your personal voice |

Voice names match loosely (`en-us-aria-neural` == `en-US-AriaNeural`).
Per-user voices are stored in `user_voices.json` next to `config.json` and
apply to host-audio playback only.

## Building the exe

Run `build.bat` → produces `dist/twitchTTS.exe`. The same binary hosts the
engine via a hidden `--engine` flag.

## Linux / headless server

The app runs on Linux: the full tray app on desktop (needs an X display or
XWayland, python3-tk, and python3-gi for the tray right-click menu; left click
opens the window, right click shows Open/Mute/About/Exit as on Windows), or a headless engine service on servers.
Windows-only bits: SAPI system voices (the engine falls back to edge and
the mode selector hides "System (offline)") and host-audio playback on
headless machines (audio plays in the browser UI instead).

```bash
# installs everything into a venv. On a desktop it adds a "Twitch TTS"
# launcher to the app menu (pin it to the dock); on a headless box it sets
# up a systemd user service instead (Ubuntu/Debian-ish):
./install_linux.sh

# desktop: open "Twitch TTS" from the app menu, or from a terminal:
~/.local/share/twitchtts/venv/bin/python twitchtts_app.py

# remove launcher, icon, venv and service (keeps the checkout + config):
./uninstall_linux.sh

# headless logs:
journalctl --user -u twitchtts -f
```

Config is `config.json` next to the sources (auto-created on first run).
The engine binds to `127.0.0.1` — from another machine, use an SSH tunnel
and open `http://localhost:8080/index.html`:

```bash
ssh -L 8080:localhost:8080 -L 8081:localhost:8081 user@server
```

## Architecture

- `app.py` — asyncio service: anonymous Twitch IRC, HTTP API (`http_port`),
  SSE event stream (`stream_port`)
- `audio.py` — `AudioPlayer` queue thread (pygame-ce) with skip/clear, live
  volume/mute, and 5 ms fade in/out
- `emotes.py` / `sanitize.py` — BTTV/FFZ/7TV emote loading and text cleaning
- `piper_engine.py` — optional Piper engine: voice download, loading, WAV synthesis
- `config.py` — config path resolution (repo dir for source, `%APPDATA%` for exe)
- `twitchtts_app.py` — tray shell / control window; single-instance guard

SSE events: `log`, `voices`, `voice`, `chat`, `now_playing`, `control`.
API routes (loopback-only): `/api/voices`, `/api/tts`, `/api/config` (GET/POST),
`/api/status`, `/api/control`, `/api/voice`.

## License

Source code: MIT — see [LICENSE.md](LICENSE.md). The Windows exe bundles
piper-tts (GPL-3.0-or-later) and is therefore distributed under the GPL-3.0.
Bundled dependencies and their licenses are listed in
[THIRD-PARTY-SOFTWARE.md](THIRD-PARTY-SOFTWARE.md).

## Links

Part of the [vhsgreed](https://vhsgreed.win) toolset: data, code, and methods in the open.
