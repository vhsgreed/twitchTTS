"""Standalone tray shell for the Twitch TTS Engine (Windows primary).

Runs the engine (``app.py``) as a local subprocess and provides:

* a system tray icon whose color reflects engine state
  (green = ok, red = error, grey = offline) with an
  Open / Mute / About / Exit menu;
* a simple native window (mute, skip, voice, volume, now playing, log);
* minimize-to-tray: closing the window keeps the engine running.

When frozen with PyInstaller the same executable re-runs itself with
``--engine`` to host the engine.
"""

from __future__ import annotations

import importlib.util
import json
import os
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from tkinter import messagebox, ttk

from config import get_config_path

VERSION = "0.3.0"

def _piper_installed() -> bool:
    try:
        return importlib.util.find_spec("piper") is not None
    except (ImportError, ValueError):
        return False


MODE_LABELS = {"Neural (edge-tts)": "edge"}
if _piper_installed():
    MODE_LABELS["Piper (offline)"] = "piper"
if os.name == "nt":
    # Windows SAPI voices exist only on Windows; hide on other OSes.
    MODE_LABELS["System (offline)"] = "system"
MODE_KEYS = {key: label for label, key in MODE_LABELS.items()}
# Next to the executable when frozen (PyInstaller), next to this file otherwise.
BASE_DIR = os.path.dirname(
    os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)
)

COLORS = {
    "ok": (46, 160, 67),
    "starting": (210, 160, 30),
    "error": (200, 50, 50),
    "offline": (140, 140, 140),
}


def _read_config() -> dict:
    # Resolve via config.py: repo dir for source runs, %APPDATA%\TwitchTTS
    # for the frozen exe. Reading next to the exe silently ignored the
    # persisted settings on frozen builds (config lives in app data).
    try:
        with open(get_config_path(), encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def engine_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--engine"]
    return [sys.executable, os.path.join(BASE_DIR, "app.py")]


class TwitchTTSShell:
    def __init__(self) -> None:
        self.engine: subprocess.Popen | None = None
        self.state = "offline"
        self.muted = False
        self.close_to_tray = True
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.port = 8080
        self.stream_port = 8081
        self._stop = threading.Event()
        self._voice_by_label: dict[str, str] = {}

        self._build_window()
        self._build_tray()
        self._start_engine()
        threading.Thread(target=self._poll_status, daemon=True).start()
        threading.Thread(target=self._sse_reader, daemon=True).start()
        self.root.after(100, self._drain_log_queue)

    # ------------------------------------------------------------------ tray
    def _build_tray(self) -> None:
        if sys.platform.startswith("linux"):
            # pystray's xorg fallback cannot show menus. AppIndicator (GNOME,
            # KDE) and GTK StatusIcon can; StatusIcon needs GTK on X11, so
            # pin GDK to XWayland before pystray imports Gtk.
            os.environ.setdefault("GDK_BACKEND", "x11")
            if "PYSTRAY_BACKEND" not in os.environ:
                # GTK StatusIcon matches Windows: left click opens the window,
                # right click shows the menu. AppIndicator only has a menu.
                for backend in ("gtk", "appindicator"):
                    if _pystray_backend_ok(backend):
                        os.environ["PYSTRAY_BACKEND"] = backend
                        break
        import pystray  # GUI dep; only needed in shell mode (not --engine)

        def on_tk(fn):
            # pystray calls back on its own thread; Tk is single-threaded.
            return lambda icon=None, item=None: self.root.after(0, fn)

        menu = pystray.Menu(
            pystray.MenuItem("Open", on_tk(self.open_window), default=True),
            pystray.MenuItem("Mute", on_tk(self.toggle_mute), checked=lambda item: self.muted),
            pystray.MenuItem("About", on_tk(self.about)),
            pystray.MenuItem("Exit", on_tk(self.exit_app)),
        )
        self.tray = pystray.Icon(
            "twitchtts", self._tray_image("offline"), "Twitch TTS Engine", menu
        )
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _tray_image(self, state: str, muted: bool = False) -> Image.Image:
        from PIL import Image, ImageDraw

        color = COLORS.get(state, COLORS["offline"])
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((4, 4, 60, 60), fill=color, outline=(30, 30, 30), width=3)
        d.polygon([(24, 25), (34, 25), (46, 15), (46, 49), (34, 39), (24, 39)], fill=(255, 255, 255))
        if muted:
            d.line((12, 12, 52, 52), fill=(220, 40, 40), width=7)
        return img

    def _refresh_tray(self) -> None:
        suffix = " - muted" if self.muted else ""
        self.tray.icon = self._tray_image(self.state, self.muted)
        self.tray.title = f"Twitch TTS Engine - {self.state}{suffix}"
        self.tray.update_menu()

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self._refresh_tray()

    # ---------------------------------------------------------------- window
    def _build_window(self) -> None:
        # className sets the X11 WM_CLASS (Tk normalises it to "Twitchtts");
        # the Linux .desktop launcher's StartupWMClass must match it so the
        # dock groups the window under the launcher icon.
        self.root = tk.Tk(className="twitchtts")
        self.root.title("Twitch TTS Engine")
        try:
            from PIL import ImageTk

            self._window_icon = ImageTk.PhotoImage(self._tray_image("ok"))
            self.root.iconphoto(True, self._window_icon)
        except Exception:
            pass  # cosmetic only
        # Final size is set after the widgets exist (see _fit_window).
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        pad = {"padx": 8, "pady": 4}
        frame = ttk.Frame(self.root, padding=8)
        frame.pack(fill="both", expand=True)

        controls = ttk.Frame(frame)
        controls.pack(fill="x", **pad)
        self.mute_btn = ttk.Button(controls, text="Mute", command=self.toggle_mute, width=8)
        self.mute_btn.pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="Skip", command=self.skip, width=8).pack(side="left", padx=(0, 12))

        ttk.Label(controls, text="Engine:").pack(side="left")
        self.mode_var = tk.StringVar()
        self.mode_box = ttk.Combobox(
            controls,
            textvariable=self.mode_var,
            state="readonly",
            width=17,
            values=list(MODE_LABELS.keys()),
        )
        self.mode_box.pack(side="left", padx=6)
        self.mode_var.set(next(iter(MODE_LABELS)))
        if len(MODE_LABELS) < 2:
            # Only one engine on this OS: a one-item dropdown renders as an
            # empty collapsed popdown on Linux Tk, so show it read-only.
            self.mode_box.config(state="disabled")
        self.mode_box.bind("<<ComboboxSelected>>", self._mode_selected)

        # Voice comes after Engine: its list depends on the engine.
        ttk.Label(controls, text="Voice:").pack(side="left")
        self.voice_var = tk.StringVar()
        self.voice_box = ttk.Combobox(
            controls, textvariable=self.voice_var, state="readonly", width=28
        )
        self.voice_box.pack(side="left", padx=6)
        self.voice_box.bind("<<ComboboxSelected>>", self._voice_selected)

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, **pad)

        # Packed before `left` so a narrow window squeezes the log, not the slider.
        right = ttk.Frame(body)
        right.pack(side="right", fill="y", padx=(10, 0))

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        now = ttk.Frame(left)
        now.pack(fill="x")
        ttk.Label(now, text="Now Playing", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.now_label = ttk.Label(now, text="—", wraplength=440, justify="left")
        self.now_label.pack(anchor="w", pady=(2, 0))
        self.queue_label = ttk.Label(now, text="", foreground="#666666")
        self.queue_label.pack(anchor="w")

        log_frame = ttk.Frame(left)
        log_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.log_text = tk.Text(log_frame, height=10, state="disabled", wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scroll.set)

        ttk.Label(right, text="Volume").pack()
        self.volume_var = tk.DoubleVar(value=80)
        self.volume_scale = ttk.Scale(
            right,
            from_=100,
            to=0,
            orient="vertical",
            variable=self.volume_var,
            command=self._volume_drag,
        )
        self.volume_scale.pack(fill="y", expand=True)
        self.volume_label = ttk.Label(right, text="80%", width=5)
        self.volume_label.pack(pady=(2, 0))

        bottom = ttk.Frame(frame)
        bottom.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Button(bottom, text="About", command=self.about, width=8).pack(side="left")
        self.status_label = ttk.Label(bottom, text="● offline", foreground="#8c8c8c")
        self.status_label.pack(side="left", padx=(8, 0))
        ttk.Button(bottom, text="Options...", command=self._open_options, width=10).pack(side="right")
        self._fit_window()

    def _fit_window(self) -> None:
        """Size the window to its widgets instead of a fixed 560 px.

        Linux Tk fonts are wider than Segoe UI on Windows, so a fixed width
        clipped the volume slider and the engine dropdown there.
        """
        self.root.update_idletasks()
        width = max(560, self.root.winfo_reqwidth() + 24)  # a little slack
        self.root.geometry(f"{width}x440")
        self.root.minsize(width, 360)

    def hide_window(self) -> None:
        self.root.withdraw()

    def open_window(self, icon=None, item=None) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _log(self, line: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _drain_log_queue(self) -> None:
        while True:
            try:
                self._log(self.log_queue.get_nowait())
            except queue.Empty:
                break
        self.root.after(100, self._drain_log_queue)

    # ---------------------------------------------------------------- engine
    def _start_engine(self) -> None:
        self._log("Starting engine...")
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW
        self.engine = subprocess.Popen(
            engine_command(),
            cwd=BASE_DIR,
            stdin=subprocess.DEVNULL,  # engine's console prompt must not grab the terminal
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
            preexec_fn=_die_with_parent if sys.platform.startswith("linux") else None,
        )
        threading.Thread(target=self._engine_reader, daemon=True).start()
        # Re-read config: the engine creates config.json from the example.
        cfg = _read_config()
        self.port = int(cfg.get("http_port", 8080))
        self.stream_port = int(cfg.get("stream_port", 8081))
        self.close_to_tray = bool(cfg.get("close_to_tray", True))
        self._apply_close_behavior()
        threading.Thread(target=self._load_voices, kwargs={"retries": 45}, daemon=True).start()

    def _apply_close_behavior(self) -> None:
        """Close button minimizes to tray or exits the whole app, per config."""
        if self.close_to_tray:
            self.root.protocol("WM_DELETE_WINDOW", self.hide_window)
        else:
            self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

    def _engine_reader(self) -> None:
        assert self.engine is not None and self.engine.stdout is not None
        for line in self.engine.stdout:
            stripped = line.rstrip()
            # app_log() lines arrive over SSE too; only surface unexpected
            # stdout here (tracebacks, warnings) to avoid double logging.
            if re.match(r"^\[\d{2}:\d{2}:\d{2}\] ", stripped):
                continue
            self.log_queue.put(stripped)
        self.log_queue.put("[engine exited]")

    def _api(self, path: str, timeout: float = 4.0) -> dict | None:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=timeout
            ) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return None

    def _post(self, path: str, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}{path}", data=data,
                headers={"Content-Type": "application/json"}, method="POST",
            )
            urllib.request.urlopen(req, timeout=4.0).read()
        except (OSError, urllib.error.URLError):
            pass

    # ------------------------------------------------------------- statusing
    def _poll_status(self) -> None:
        while not self._stop.is_set():
            if self.engine is not None and self.engine.poll() is not None:
                self._set_state("offline")
                self.root.after(0, lambda: self.status_label.config(text="● offline", foreground="#8c8c8c"))
            else:
                status = self._api("/api/status")
                if status is None and self.engine is not None:
                    # Process alive but API not listening yet: still booting.
                    self._set_state("starting")
                    self.root.after(0, lambda: self.status_label.config(text="● starting…", foreground="#d2a01e"))
                elif status is None:
                    self._set_state("offline")
                    self.root.after(0, lambda: self.status_label.config(text="● offline", foreground="#8c8c8c"))
                else:
                    state = status.get("status", "error")
                    self._set_state(state)
                    text = {
                        "ok": "● engine running",
                        "starting": "● starting…",
                        "error": "● error — check log",
                    }.get(state, "● offline")
                    color = {"ok": "#2ea043", "starting": "#d2a01e", "error": "#c83232"}.get(state, "#8c8c8c")
                    self.root.after(0, lambda t=text, c=color: self.status_label.config(text=t, foreground=c))
            self._stop.wait(2.0)

    def _sse_reader(self) -> None:
        url = f"http://127.0.0.1:{self.stream_port}/"
        while not self._stop.is_set():
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    for raw in resp:
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        try:
                            evt = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            continue
                        self._handle_event(evt)
            except (OSError, urllib.error.URLError):
                self._stop.wait(3.0)

    def _handle_event(self, evt: dict) -> None:
        etype = evt.get("type")
        if etype == "log":
            self.log_queue.put(f"[{evt.get('time', '')}] {evt.get('message', '')}")
        elif etype == "voice":
            voice = evt.get("voice")
            mode = evt.get("mode")
            if mode:
                self.root.after(0, lambda m=mode: self._set_mode_var(m))
                # Reload the list for this engine; it preselects the voice.
                threading.Thread(target=self._load_voices, daemon=True).start()
            elif voice:
                self.root.after(0, lambda v=voice: self._select_voice(v))
        elif etype == "voices":
            voices = evt.get("voices") or []
            if voices:
                threading.Thread(target=self._apply_voices, args=(voices,), daemon=True).start()
        elif etype == "now_playing":
            self.root.after(0, lambda: self.now_label.config(text=f"{evt.get('user', '')}: {evt.get('text', '')}"))
        elif etype == "control":
            self.root.after(0, self._apply_control_event, evt)

    def _apply_control_event(self, evt: dict) -> None:
        if "queue" in evt:
            self.queue_label.config(text=f"queue: {evt['queue']}")
        if "volume" in evt:
            self.volume_var.set(int(float(evt["volume"]) * 100))
            self.volume_label.config(text=f"{int(float(evt['volume']) * 100)}%")
        if "muted" in evt:
            self.muted = bool(evt["muted"])
            self.mute_btn.config(text="Unmute" if self.muted else "Mute")
            self._refresh_tray()

    # -------------------------------------------------------------- controls
    def toggle_mute(self, icon=None, item=None) -> None:
        # Ask the engine to flip state; update locally optimistically and let
        # the SSE control events re-sync if the request failed.
        self._post("/api/control", {"action": "toggle_mute"})
        self.muted = not self.muted
        self.mute_btn.config(text="Unmute" if self.muted else "Mute")
        self._refresh_tray()

    def skip(self) -> None:
        self._post("/api/control", {"action": "skip"})

    def _voice_selected(self, _event=None) -> None:
        # The combobox shows labels like "en-US-JennyNeural (Female, en-US)";
        # the engine expects the ShortName.
        label = self.voice_var.get()
        voice = self._voice_by_label.get(label, label)
        self._post("/api/voice", {"voice": voice})

    def _set_mode_var(self, key: str) -> None:
        self.mode_var.set(MODE_KEYS.get(key, "Neural (edge-tts)"))

    def _mode_selected(self, _event=None) -> None:
        key = MODE_LABELS.get(self.mode_var.get(), "edge")
        self._post("/api/voice", {"mode": key})
        # The engine's "voice" event reloads the matching voice list; this
        # covers an engine too old to send one.
        threading.Thread(target=self._load_voices, daemon=True).start()

    def _volume_drag(self, _value=None) -> None:
        self.volume_label.config(text=f"{int(self.volume_var.get())}%")

    def _volume_released(self, _event=None) -> None:
        self._post("/api/control", {"action": "volume", "value": self.volume_var.get() / 100.0})

    def _load_voices(self, retries: int = 0) -> None:
        data = self._api("/api/voices")
        # The engine takes a while to come up (emote + voice lists load
        # first); the startup call retries until the API answers.
        while not data and retries > 0 and not self._stop.is_set():
            retries -= 1
            self._stop.wait(2.0)
            data = self._api("/api/voices")
        if not data:
            return
        self._apply_voices(data)

    def _apply_voices(self, data: list) -> None:
        options = []
        by_label: dict[str, str] = {}
        for v in data:
            if not isinstance(v, dict):
                continue
            # /api/voices returns {name, gender, locale, label}.
            name = v.get("name") or v.get("ShortName") or v.get("Name")
            if not name:
                continue
            label = v.get("label") or name
            by_label[label] = name
            options.append(label)
        self._voice_by_label = by_label
        self.root.after(0, lambda: self.voice_box.config(values=options))
        # Show the voice the active engine really uses (each engine keeps
        # its own voice, so this is never another engine's voice name).
        cfg = self._api("/api/config")
        if cfg:
            current = cfg.get("active_voice", cfg.get("tts_voice", ""))
            self.root.after(0, lambda c=current: self._select_voice(c))
            self.root.after(0, lambda m=cfg.get("tts_mode", "edge"): self._set_mode_var(m))

    def _select_voice(self, name: str) -> None:
        if not name:
            self.voice_var.set("(system default)")
            return
        for label, voice in self._voice_by_label.items():
            if voice == name:
                self.voice_var.set(label)
                return
        self.voice_var.set(name)

    def _restart_engine(self) -> None:
        """Stop the engine subprocess and start it again (picks up config)."""
        if self.engine is not None and self.engine.poll() is None:
            self.engine.terminate()
            try:
                self.engine.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.engine.kill()
        self._log("Restarting engine...")
        self._start_engine()

    def _open_options(self) -> None:
        """Options window: edit config.json from the GUI instead of by hand."""
        self.root.deiconify()  # dialogs need a viewable parent (tray-only case)
        cfg = self._api("/api/config") or {}
        voices = self._api("/api/voices") or []

        win = tk.Toplevel(self.root)
        win.title("Twitch TTS Options")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill="both", expand=True)

        rows = []

        def add_row(label: str, widget: tk.Widget) -> None:
            rows.append((label, widget))

        channel_var = tk.StringVar(value=cfg.get("twitch_channel", ""))
        add_row("Twitch channel", ttk.Entry(frame, textvariable=channel_var, width=28))

        # Engine first, then a voice from that engine's list. Each engine
        # keeps its own voice (tts_voice / piper_voice / system_voice).
        voice_keys = {"edge": "tts_voice", "piper": "piper_voice", "system": "system_voice"}
        chosen = {mode: str(cfg.get(key) or "") for mode, key in voice_keys.items()}
        if not chosen["piper"]:
            chosen["piper"] = "en_US-joe-medium"
        start_mode = cfg.get("tts_mode", "edge")
        engine_var = tk.StringVar(value=MODE_KEYS.get(start_mode, next(iter(MODE_LABELS))))
        engine_box = ttk.Combobox(
            frame, textvariable=engine_var, state="readonly", width=28,
            values=list(MODE_LABELS.keys()),
        )
        add_row("Engine", engine_box)

        voice_var = tk.StringVar()
        voice_box = ttk.Combobox(frame, textvariable=voice_var, state="readonly", width=28)
        by_label: dict[str, str] = {}
        voice_cache: dict[str, list] = {start_mode: voices}
        current_mode = {"key": None}
        add_row("Voice", voice_box)
        voice_hint = ttk.Label(frame, text="", foreground="#666666")

        def remember_voice() -> None:
            mode = current_mode["key"]
            if mode:
                text = voice_var.get().strip()
                chosen[mode] = by_label.get(text, "" if text == "(system default)" else text)

        def show_engine(_event=None) -> None:
            remember_voice()
            mode = MODE_LABELS.get(engine_var.get(), "edge")
            current_mode["key"] = mode
            if mode not in voice_cache:
                voice_cache[mode] = self._api(f"/api/voices?mode={mode}", timeout=25.0) or []
            by_label.clear()
            options = []
            for v in voice_cache[mode]:
                if not isinstance(v, dict) or not v.get("name"):
                    continue
                label = v.get("label") or v["name"]
                by_label[label] = v["name"]
                options.append(label)
            if mode == "system":
                options.insert(0, "(system default)")
            voice_box.config(values=options, state="normal" if mode == "piper" else "readonly")
            want = chosen.get(mode, "")
            label = next((lb for lb, n in by_label.items() if n == want), None)
            if label is None and mode == "edge" and options:
                label = next((lb for lb in options if lb.startswith("en-US-JennyNeural")), options[0])
            voice_var.set(label or want or ("(system default)" if mode == "system" else ""))
            voice_hint.config(
                text="Type any Piper voice name to download it (e.g. en_GB-alba-medium)."
                if mode == "piper" else ""
            )

        engine_box.bind("<<ComboboxSelected>>", show_engine)

        prefix_var = tk.StringVar(value=cfg.get("command_prefix", "!tts"))
        prefix_entry = ttk.Entry(frame, textvariable=prefix_var, width=28)
        add_row("Command prefix", prefix_entry)

        require_prefix_var = tk.BooleanVar(value=bool(cfg.get("require_prefix", True)))

        def _toggle_prefix_entry() -> None:
            prefix_entry.config(state="normal" if require_prefix_var.get() else "disabled")

        require_prefix_var.trace_add("write", lambda *_: _toggle_prefix_entry())
        _toggle_prefix_entry()
        add_row(
            "Require command prefix",
            ttk.Checkbutton(frame, variable=require_prefix_var, command=_toggle_prefix_entry),
        )

        cooldown_var = tk.StringVar(value=str(cfg.get("cooldown_seconds", 3)))
        add_row("Cooldown (seconds)", ttk.Spinbox(frame, from_=0, to=120, textvariable=cooldown_var, width=8))

        maxchars_var = tk.StringVar(value=str(cfg.get("max_chars", 200)))
        add_row("Max message length", ttk.Spinbox(frame, from_=10, to=500, textvariable=maxchars_var, width=8))

        special_var = tk.StringVar(value=", ".join(cfg.get("special_users", [])))
        add_row("Special users (comma separated)", ttk.Entry(frame, textvariable=special_var, width=28))

        audio = cfg.get("audio") if isinstance(cfg.get("audio"), dict) else {}
        volume_var = tk.DoubleVar(value=float(audio.get("volume", 0.8)) * 100)
        volume_scale = ttk.Scale(frame, from_=0, to=100, variable=volume_var, length=200)
        add_row("Audio volume", volume_scale)

        muted_var = tk.BooleanVar(value=bool(audio.get("muted", False)))
        add_row("Muted by default", ttk.Checkbutton(frame, variable=muted_var))

        queue_var = tk.StringVar(value=str(audio.get("queue_size", 50)))
        add_row("Audio queue size", ttk.Spinbox(frame, from_=1, to=500, textvariable=queue_var, width=8))

        close_to_tray_var = tk.BooleanVar(value=bool(cfg.get("close_to_tray", True)))
        add_row("Close button minimizes to tray", ttk.Checkbutton(frame, variable=close_to_tray_var))

        fallback_var = tk.BooleanVar(value=bool(cfg.get("tts_fallback", True)))
        add_row("Fall back to other engines on failure", ttk.Checkbutton(frame, variable=fallback_var))

        grid_row = 0
        for label, widget in rows:
            ttk.Label(frame, text=label).grid(row=grid_row, column=0, sticky="w", padx=(0, 8), pady=3)
            widget.grid(row=grid_row, column=1, sticky="w", pady=3)
            grid_row += 1
            if widget is voice_box:
                voice_hint.grid(row=grid_row, column=1, sticky="w")
                grid_row += 1
        rows = [None] * grid_row  # later rows are placed after these
        show_engine()

        ttk.Label(
            frame,
            text=(
                "Most settings apply immediately; channel, ports and audio "
                "device need a restart (Save & Restart applies everything now)."
            ),
            foreground="#666666",
        ).grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(
            frame,
            text=f"Config file: {get_config_path()}",
            foreground="#888888",
        ).grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        def collect() -> dict:
            special = [u.strip() for u in special_var.get().split(",") if u.strip()]
            remember_voice()
            return {
                "twitch_channel": channel_var.get().strip(),
                "tts_mode": current_mode["key"] or "edge",
                "tts_voice": chosen["edge"] or cfg.get("tts_voice", "en-US-JennyNeural"),
                "system_voice": chosen["system"],
                "piper_voice": chosen["piper"].strip() or "en_US-joe-medium",
                "command_prefix": prefix_var.get().strip() or "!tts",
                "require_prefix": require_prefix_var.get(),
                "cooldown_seconds": int(float(cooldown_var.get() or 0)),
                "max_chars": int(float(maxchars_var.get() or 200)),
                "special_users": special,
                "close_to_tray": close_to_tray_var.get(),
                "tts_fallback": fallback_var.get(),
                "audio": {
                    "volume": max(0.0, min(1.0, volume_var.get() / 100.0)),
                    "muted": muted_var.get(),
                    "queue_size": int(float(queue_var.get() or 50)),
                },
            }

        def save() -> bool:
            try:
                payload = collect()
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/api/config",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=6.0) as resp:
                    resp.read()
            except Exception as exc:  # noqa: BLE001 - surface any failure to the user
                self._log(f"Could not save options: {exc}")
                messagebox.showerror(
                    "Twitch TTS Options",
                    f"Could not save options:\n{exc}",
                    parent=win,
                )
                return False
            self._log("Options saved.")
            # Engine or voice may have changed: resync the main window.
            threading.Thread(target=self._load_voices, daemon=True).start()
            return True

        def on_save() -> None:
            if save():
                self.close_to_tray = close_to_tray_var.get()
                self._apply_close_behavior()
                win.destroy()

        def on_save_restart() -> None:
            if save():
                self.close_to_tray = close_to_tray_var.get()
                self._apply_close_behavior()
                win.destroy()
                self._restart_engine()

        btns = ttk.Frame(frame)
        btns.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Save", command=on_save).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Save & Restart", command=on_save_restart).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="left")

    def _open_license(self) -> None:
        license_path = os.path.join(BASE_DIR, "LICENSE.md")
        opener = getattr(os, "startfile", None)
        if opener is not None and os.path.isfile(license_path):
            try:
                opener(license_path)
                return
            except OSError:
                pass
        webbrowser.open("https://github.com/vhsgreed/twitchTTS/blob/master/LICENSE.md")

    def _open_notices(self) -> None:
        notices_path = os.path.join(BASE_DIR, "THIRD-PARTY-SOFTWARE.md")
        opener = getattr(os, "startfile", None)
        if opener is not None and os.path.isfile(notices_path):
            try:
                opener(notices_path)
                return
            except OSError:
                pass
        webbrowser.open("https://github.com/vhsgreed/twitchTTS/blob/master/THIRD-PARTY-SOFTWARE.md")

    def _open_repo(self) -> None:
        webbrowser.open("https://github.com/vhsgreed/twitchTTS")

    def about(self, icon=None, item=None) -> None:
        self.root.deiconify()  # dialogs need a viewable parent (tray-only case)
        win = tk.Toplevel(self.root)
        win.title("About Twitch TTS Engine")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        frame = ttk.Frame(win, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Twitch TTS Engine", font=("Segoe UI", 13, "bold")).pack()
        ttk.Label(
            frame,
            text=(
                f"Version {VERSION}\n\n"
                "Real-time text-to-speech for Twitch chat.\n\n"
                "Licensed under the MIT License.\n"
                f"Config: {get_config_path()}"
            ),
            justify="center",
        ).pack(pady=(4, 10))

        btns = ttk.Frame(frame)
        btns.pack()
        ttk.Button(btns, text="View MIT License", command=self._open_license).pack(side="left", padx=4)
        ttk.Button(btns, text="Third-Party Notices", command=self._open_notices).pack(side="left", padx=4)
        ttk.Button(btns, text="Repository", command=self._open_repo).pack(side="left", padx=4)
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="left", padx=4)

    def exit_app(self, icon=None, item=None) -> None:
        if self._stop.is_set():
            return  # already shutting down (menu + signal, double click)
        self._stop.set()
        if self.engine is not None and self.engine.poll() is None:
            self.engine.terminate()
            try:
                self.engine.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.engine.kill()
        try:
            self.tray.stop()
        except Exception:
            pass
        self.root.quit()
        self.root.destroy()

    def _install_signal_handlers(self) -> None:
        """Ctrl+C, kill and closing the terminal quit like tray -> Exit."""
        def handler(signum, _frame):
            self.root.after(0, self.exit_app)

        for name in ("SIGINT", "SIGTERM", "SIGHUP"):
            sig = getattr(signal, name, None)
            if sig is not None:
                signal.signal(sig, handler)

        if hasattr(signal, "SIGUSR1"):
            # A second launch (e.g. clicking the dock icon while the window
            # sits in the tray) signals us to show the window and exits.
            # The dock's right-click actions (--mute, --about, --exit) write
            # their command to a file next to the lock before signalling.
            signal.signal(signal.SIGUSR1, lambda *_: self.root.after(0, self._remote_command))

        # Python only runs signal handlers between bytecodes; Tk's mainloop
        # sits in C, so wake the interpreter regularly.
        def tick():
            if not self._stop.is_set():
                self.root.after(250, tick)
        tick()

    def _remote_command(self) -> None:
        action = _read_remote_action()
        handler = {
            "mute": self.toggle_mute,
            "about": self.about,
            "exit": self.exit_app,
        }.get(action, self.open_window)
        handler()

    def run(self) -> None:
        self.volume_scale.bind("<ButtonRelease-1>", self._volume_released)
        self._install_signal_handlers()
        self.root.mainloop()


def _pystray_backend_ok(name: str) -> bool:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk  # noqa: F401

        if name == "appindicator":
            try:
                gi.require_version("AyatanaAppIndicator3", "0.1")
            except ValueError:
                gi.require_version("AppIndicator3", "0.1")
        return True
    except (ImportError, ValueError):
        return False


def _die_with_parent() -> None:
    """Linux: SIGTERM the engine when the shell process dies for any reason."""
    import ctypes

    PR_SET_PDEATHSIG = 1
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)


_SINGLE_INSTANCE_MUTEX = None
_SINGLE_INSTANCE_LOCK = None

# Command-line actions, matching the tray menu. The Linux .desktop file
# exposes them as right-click actions on the dock icon.
REMOTE_ACTIONS = ("open", "mute", "about", "exit")


def _requested_action() -> str:
    for action in REMOTE_ACTIONS:
        if f"--{action}" in sys.argv:
            return action
    return "open"


def _remote_command_path() -> str:
    run_dir = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(run_dir, f"twitchtts-{os.getuid()}.cmd")


def _read_remote_action() -> str:
    """Read and consume the action a second launch left for us."""
    try:
        path = _remote_command_path()
        with open(path, encoding="utf-8") as fh:
            action = fh.read().strip()
        os.remove(path)
    except (OSError, AttributeError):
        return "open"
    return action if action in REMOTE_ACTIONS else "open"


def _claim_single_instance_posix(action: str = "open") -> bool:
    """Linux/macOS: flock a lock file holding our pid.

    A second instance finds the lock taken, sends SIGUSR1 to the pid in the
    file (the running shell then shows its window) and exits.
    """
    global _SINGLE_INSTANCE_LOCK
    try:
        import fcntl

        run_dir = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
        path = os.path.join(run_dir, f"twitchtts-{os.getuid()}.lock")
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            try:
                pid = int(os.read(fd, 32).decode().strip() or 0)
                if pid > 0:
                    cmd = _remote_command_path()
                    with open(os.open(cmd, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
                        fh.write(action)
                    os.kill(pid, signal.SIGUSR1)
            except (ValueError, OSError):
                pass
            os.close(fd)
            return False
        # SIGUSR1 terminates by default; ignore it until the shell installs
        # its handler, so a fast double launch cannot kill this instance.
        signal.signal(signal.SIGUSR1, signal.SIG_IGN)
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        _SINGLE_INSTANCE_LOCK = fd  # held (and locked) for the process lifetime
        return True
    except Exception:
        return True  # never block startup on a guard failure


def _claim_single_instance(action: str = "open") -> bool:
    """Claim a process-wide mutex; focus the existing window if one is open.

    Returns True when this process may keep running, False when another
    instance is already active (its window was brought to the front and
    this process should exit). Windows uses a named mutex, other systems a
    lock file. The guard must not affect ``--engine`` subprocesses, so it
    is only called from the tray-shell path in ``main()``.
    """
    global _SINGLE_INSTANCE_MUTEX
    if os.name != "nt":
        return _claim_single_instance_posix(action)
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR,
        ]
        kernel32.GetLastError.restype = wintypes.DWORD
        user32.FindWindowW.restype = wintypes.HWND
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]

        handle = kernel32.CreateMutexW(None, False, "Local\\TwitchTTS.SingleInstance")
        if not handle:
            return True
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            # Bring the running instance's window to the front.
            hwnd = user32.FindWindowW(None, "Twitch TTS Engine")
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE (also un-hides)
                user32.SetForegroundWindow(hwnd)
            return False
        # Keep the handle for the process lifetime; closing it would
        # release the mutex and allow a second instance.
        _SINGLE_INSTANCE_MUTEX = handle
        return True
    except Exception:
        # Never block startup on a guard failure.
        return True


def main() -> None:
    if "--engine" in sys.argv:
        # Strip our flag before importing app: its argparse runs at import
        # time and would reject the unknown argument.
        sys.argv = [arg for arg in sys.argv if arg != "--engine"]
        import app

        if hasattr(signal, "SIGTERM"):
            # Treat terminate() from the shell like Ctrl+C so cleanup runs.
            signal.signal(signal.SIGTERM, signal.default_int_handler)
        try:
            import asyncio

            asyncio.run(app.main())
        except KeyboardInterrupt:
            pass
        finally:
            app.tts_executor.shutdown(wait=False)
            if app.audio_player is not None:
                app.audio_player.shutdown()
        return
    action = _requested_action()
    if not _claim_single_instance(action):
        sys.exit(0)
    if action == "exit":
        sys.exit(0)  # nothing running, nothing to quit
    TwitchTTSShell().run()


if __name__ == "__main__":
    main()
