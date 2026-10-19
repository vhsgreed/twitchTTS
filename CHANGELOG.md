# Changelog

All notable changes to this project are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-10-19

### Added

- Piper offline neural voices as a third engine ("Piper (offline)"), on
  Windows (bundled in the exe) and Linux. The default voice,
  `en_US-joe-medium` (CC0), downloads on first start (~60 MB).
- Automatic fallback: when edge-tts fails, the message is spoken with Piper
  (then Windows SAPI) instead of being dropped, and edge-tts is retried a
  minute later. Turn off with `tts_fallback: false` or in Options.
- Each engine keeps its own voice (`tts_voice` for edge-tts, `piper_voice`,
  `system_voice` for SAPI); switching engine switches to that engine's voice.
- Options: "Engine" then "Voice" (the list follows the chosen engine), and
  "Fall back to other engines on failure".
- A daily GitHub Actions workflow checks that neural voices still
  synthesize with the newest edge-tts and raises the `edge-tts>=` pin in
  the requirements files and README when a newer release passes.

### Changed

- The Windows exe bundles piper-tts (GPL-3.0-or-later), so the exe is
  distributed under the GPL-3.0; the source stays MIT. It grew from about
  31 MB to about 90 MB (Piper and ONNX Runtime).
- The main window shows Engine before Voice.

### Fixed

- Switching engine left the Voice menu on the old engine's voice (e.g.
  `en-US-JennyNeural` while Piper spoke `en_US-joe-medium`).
- Linux: the window opened too narrow, hiding the volume slider and
  squeezing the engine dropdown. It now sizes itself to its controls.
- Host audio: the first syllable of Piper messages was cut off ("hello" ->
  "llo"). The 80 ms start-of-playback mute assumed every clip starts with
  silence; clips that start sooner are now padded first.

## [0.2.7] - 2026-10-18

### Fixed

- Neural voices stopped working: every message failed with
  `403, message='Invalid response status'` from Microsoft's speech service,
  which changed its handshake and now rejects edge-tts older than 7.3.0.
  The requirement is now `edge-tts>=7.3.1`. Windows: download the new exe.
  Linux: re-run `install_linux.sh` (or `venv/bin/pip install -U edge-tts`)
  and restart the app.

## [0.2.6] - 2026-10-13

### Added

- Linux: right-clicking the Twitch TTS icon in the dock or app menu now
  offers the same Open, Mute / Unmute, About and Exit actions as the tray
  menu. They act on the running app; Exit with nothing running does nothing.
  Re-run `install_linux.sh` to update the launcher.

## [0.2.5] - 2026-10-13

### Added

- Linux: `install_linux.sh` now adds a "Twitch TTS" launcher with an icon to
  the app menu on desktops, so the app can be started and pinned to the dock
  without a terminal. The window groups under the launcher icon.
- Linux: `uninstall_linux.sh` removes the launcher, icon, venv and headless
  service, leaving the checkout and `config.json` in place.
- Linux: single instance. Launching again while the app runs (for example
  from the dock while the window is hidden in the tray) shows the existing
  window instead of starting a second engine that would fight over ports
  8080/8081. Windows already behaved this way.
- Window icon matches the tray icon.

### Changed

- `install_linux.sh` also treats a Wayland session as a desktop.

## [0.2.4] - 2026-10-11

### Fixed

- Linux: tray icon had no right-click menu (pystray fell back to its xorg
  backend, which has none). The shell now uses the GTK backend when
  PyGObject is available: left click opens the window, right click shows
  Open / Mute / About / Exit, same as Windows. `install_linux.sh` creates
  the venv with `--system-site-packages` and installs `python3-gi`.
- Linux: Ctrl+C, `kill` or closing the terminal killed the shell but left
  the engine running in the background (holding ports 8080/8081 and the
  audio device). SIGINT/SIGTERM/SIGHUP now take the same path as tray ->
  Exit, and the engine is tied to the shell so it also exits if the shell
  is SIGKILLed.
- Engine subprocess handles SIGTERM like Ctrl+C, releasing the audio
  device cleanly (also applies to `systemctl --user stop twitchtts`).
- Tray menu actions ran Tk calls from the tray thread; they are now
  marshalled onto the Tk main loop.

## [0.2.3] - 2026-10-11

### Fixed

- Host audio played an octave low (half speed) with a noise burst at the
  start. pygame's `Sound(buffer=...)` takes raw samples in the mixer's
  format, but it was handed a stereo WAV file while the mixer runs mono.
  MP3s are now decoded straight to the mixer's actual rate and channel
  count.
- Linux: tray shell crashed on the first status update (`UnicodeEncodeError`;
  the X11 tray backend encodes titles as Latin-1). Tray title is ASCII now.
- Linux: host audio silently fell back to browser mode because `pygame-ce`
  was missing from `requirements-linux.txt`.
- Voice selector stayed empty when the engine took longer to boot than the
  shell's single startup request. The shell now retries and also applies
  the engine's pushed voice list.
- Engine selector rendered as an empty collapsed menu on Linux, where
  edge-tts is the only engine. It now shows the engine and is read-only.
- Status showed "error - check log" while the engine was still booting.
  New amber "starting" state until the first IRC connect.
- About/license links pointed to the old repository location.

## [0.2.2] - 2026-08-21

### Added

- `require_prefix` option: disable the `!tts` prefix requirement entirely.
  New checkbox in Options (prefix field locks when disabled); default on.
- Linux package: `install_linux.sh` (headless systemd user service),
  `requirements-linux.txt`, XDG config dir for frozen builds, README
  section for servers (audio plays in the browser UI).
- Linux GUI: the full tray app runs on desktop Linux (python3-tk + X
  display); System (SAPI) mode is gated to Windows in both the engine and
  the tray's engine selector.

### Fixed

- Loud click/pop at the start of every host-audio message: pygame's mixer
  emits a ~50 ms noise burst when a channel starts playing, even for
  silent buffers. The channel is now held muted for the first 80 ms and
  faded in, so the burst never reaches the speakers (verified via WASAPI
  loopback capture: burst gone, audio intact).
- System TTS mode flashed a PowerShell console window on every synthesis
  (focus-stealing on stream). Child processes now use
  `CREATE_NO_WINDOW`.

### Changed

- `!voice` command feedback is log-only: confirmations no longer produce
  audio (previously every `!voice` reply was spoken aloud).

## [0.2.1] - 2026-08-21

### Added

- Single-instance guard: launching a second copy focuses the running window
  instead of crashing on a port conflict.
- System TTS engine mode (`tts_mode: "system"`): fully offline speech via
  Windows SAPI voices, switchable live via the Engine selector.

### Fixed

- Garbled Unicode in the tray window (Now Playing placeholder, status dots)
  caused by double-encoded characters.
- `close_to_tray` was ignored after restart on the frozen exe: the shell read
  `config.json` next to the binary instead of `%APPDATA%\TwitchTTS`, so the
  setting fell back to its default on every boot.
- Options window showed stale values after saving: the engine persisted config
  to disk but never updated its in-memory copy, so `/api/config` (which the
  Options window reads back) reported the pre-save values until restart.

### Changed

- Docs rework: README rewritten; `LICENSE` → `LICENSE.md`;
  `THIRD-PARTY-NOTICES.md` → `THIRD-PARTY-SOFTWARE.md`.

## [0.2.0] - 2026-08-20

### Fixed

- Tray app voice dropdown was always empty: it parsed the `/api/voices`
  response using the keys `ShortName`/`Name`, but the API returns
  `name`/`label`. The dropdown now lists every voice and preselects the
  engine's current voice from `/api/config`.
- Selecting a voice in the tray app now sends the voice ShortName (e.g.
  `en-US-JennyNeural`) instead of the display label, so the change
  actually applies.
- The frozen `twitchTTS.exe` crashed at startup with
  `ModuleNotFoundError: pystray`: `build.bat` used the system Python
  (which lacks pystray/PIL) and PyInstaller silently skipped the missing
  imports. `build.bat` now prefers `.venv\Scripts\python.exe`, and
  `--engine` mode no longer imports GUI dependencies at all.
- Host audio was disabled in the frozen exe (`No module named
  '_cffi_backend'`): pygame-ce needs cffi, which PyInstaller did not
  bundle. `build.bat` now passes `--hidden-import cffi` and
  `--hidden-import _cffi_backend`.
- The frozen app now resolves `config.json` and `LICENSE` next to the
  executable (previously it looked inside the onefile temp extraction
  directory).

### Changed

- About dialog now states the MIT license and offers a "View MIT License"
  button (opens the local `LICENSE` file) plus a repository link.
- New **Options...** window in the tray app: edit channel, voice, command
  prefix, cooldown, max length, special users and audio settings from the
  GUI. "Save & Restart" applies channel/prefix/port changes immediately.
- Options can now be saved from the GUI reliably; failures are shown in a
  dialog instead of failing silently.
- Mute/unmute button and tray action fixed (were sending the inverted
  action); the tray menu item is now checkable and the tray icon shows a
  red slash + "muted" title while muted.
- Volume slider moved to a vertical control beside the log.
- About window opens from the tray menu even when the main window is
  hidden, and an About button was added to the main window.
- New `close_to_tray` config option: the window close button can minimize
  to tray (default) or exit the whole app.
- Engine log lines are no longer shown twice in the tray window (the log
  was arriving over both SSE and the engine's stdout).
- The standalone exe now stores `config.json` in `%APPDATA%\TwitchTTS`
  (per-user app data, Windows convention) instead of next to the binary,
  so no JSON files appear where the exe is placed. Existing configs next
  to the exe are migrated automatically on first run.
- Added `THIRD-PARTY-NOTICES.md` (LGPL notices for edge-tts and pygame-ce
  plus MIT texts) and linked it from the About dialog; project stays MIT
  while remaining compliant with its LGPL dependencies.

### Added

- **`!voice` chat command** (host-audio mode): viewers can set their own
  TTS voice (`!voice <name>`, `!voice` to check, `!voice reset` to clear).
  Voices are matched loosely (case/hyphens ignored), confirmed aloud in the
  chosen voice, and remembered per user across restarts
  (`user_voices.json`).
- Standalone tray shell (`twitchtts_app.py`): native window + system tray
  with status color (green ok / red error / grey offline) and an
  open/mute/about/exit menu; minimize-to-tray keeps the engine running.
- Engine `/api/status` endpoint reporting connection and error state for
  the tray icon.
- PyInstaller build support (`build.bat`): the frozen executable hosts the
  engine via a `--engine` flag.

## [0.1.1] - 2026-08-19

### Fixed

- Host audio played synthesized speech as loud static noise. pygame's
  `Sound()` cannot decode MP3 from a buffer, so host audio is now decoded
  with `miniaudio` and re-wrapped as WAV before playback.
- `config.json` written with a UTF-8 BOM (Windows editors) no longer
  crashes the engine at startup.
- `start_tts.bat` now prefers the project virtual environment when present,
  so host audio is enabled on setups where the system Python lacks
  pygame-ce.

## [0.1.0] - 2026-08-19

### Added

- First public release of the Twitch TTS Engine.
- Anonymous Twitch IRC chat listener (no API keys required).
- Neural text-to-speech via [edge-tts](https://github.com/rany2/edge-tts)
  with fallback to browser-based synthesis.
- Host audio playback (pygame-ce) with a bounded server-side queue,
  skip/clear, live volume and mute.
- Browser control panel (OBS-ready) with mute, volume, skip, voice selection,
  "now playing" and engine log.
- Server-sent events (SSE) stream with automatic reconnection.
- Content sanitization: strips Twitch/BTTV/FFZ/7TV emotes, emojis, URLs and
  excess whitespace.
- Config-driven rules: command prefix, special users, per-user cooldown,
  message length limit.
- Local-only HTTP API with loopback origin protection.
- `--no-audio` / `--audio` command-line overrides.
- First-run auto-creation of `config.json` from `config.example.json`.
- MIT license, contributing guidelines, changelog.
