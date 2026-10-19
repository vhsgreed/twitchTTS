"""Offline neural TTS with Piper (https://github.com/OHF-Voice/piper1-gpl).

Optional engine: everything here degrades to ``available() == False`` when
the ``piper-tts`` package is not installed. Voice models (``*.onnx`` plus
``*.onnx.json``) live in ``piper-voices`` next to ``config.json`` and are
downloaded from the rhasspy/piper-voices repository on Hugging Face on
first use.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import threading
import urllib.request
import wave
from pathlib import Path

from config import get_config_dir

# CC0-licensed voice (OHF voice-datasets), safe for monetized streams.
DEFAULT_VOICE = "en_US-joe-medium"

_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "{family}/{code}/{name}/{quality}/{code}-{name}-{quality}{ext}?download=true"
)
_VOICE_RE = re.compile(
    r"^(?P<family>[a-z]{2,3})_(?P<region>[A-Z]{2})-(?P<name>[A-Za-z0-9_]+)-"
    r"(?P<quality>x_low|low|medium|high)$"
)

_loaded: dict[str, object] = {}
_load_lock = threading.Lock()
_synth_lock = threading.Lock()  # espeak phonemizer state is process-global
_download_lock = threading.Lock()


def available() -> bool:
    """True when the piper-tts package can be imported."""
    try:
        return importlib.util.find_spec("piper") is not None
    except (ImportError, ValueError):
        return False


def voices_dir() -> Path:
    return Path(get_config_dir()) / "piper-voices"


def installed_voices() -> list[str]:
    folder = voices_dir()
    if not folder.is_dir():
        return []
    return sorted(
        p.name[: -len(".onnx")]
        for p in folder.glob("*.onnx")
        if p.with_name(p.name + ".json").is_file()
    )


def list_voices() -> list[dict]:
    """Installed voices in the engine's browser-facing format."""
    result = []
    for name in installed_voices():
        locale = name.split("-", 1)[0].replace("_", "-")
        try:
            with open(voices_dir() / f"{name}.onnx.json", encoding="utf-8") as f:
                code = json.load(f).get("language", {}).get("code")
            if code:
                locale = str(code).replace("_", "-")
        except (OSError, ValueError):
            pass
        result.append(
            {"name": name, "gender": "", "locale": locale, "label": f"{name} (Piper, {locale})"}
        )
    return result


def resolve(voice: str | None, preferred: str = DEFAULT_VOICE) -> str | None:
    """An installed voice: ``voice`` if installed, else ``preferred``, else any."""
    installed = installed_voices()
    for candidate in (voice, preferred):
        if candidate and candidate in installed:
            return candidate
    return installed[0] if installed else None


def ensure_voice(name: str = DEFAULT_VOICE, log=None) -> bool:
    """Download a voice if it is missing. Returns True when it is installed."""
    match = _VOICE_RE.match(name or "")
    if not match:
        raise ValueError(f"Not a Piper voice name: {name!r} (like en_US-joe-medium)")
    with _download_lock:
        if name in installed_voices():
            return True
        folder = voices_dir()
        folder.mkdir(parents=True, exist_ok=True)
        family = match.group("family")
        args = {
            "family": family,
            "code": f"{family}_{match.group('region')}",
            "name": match.group("name"),
            "quality": match.group("quality"),
        }
        if log:
            log(f"Downloading Piper voice {name} (about 60 MB)...")
        # Config first, model last: a voice counts as installed only once
        # both files exist, and each lands via an atomic rename.
        for ext in (".onnx.json", ".onnx"):
            dest = folder / f"{name}{ext}"
            tmp = dest.with_name(dest.name + ".part")
            req = urllib.request.Request(
                _URL.format(ext=ext, **args), headers={"User-Agent": "twitchTTS"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
                while chunk := resp.read(1 << 20):
                    out.write(chunk)
            os.replace(tmp, dest)
        if log:
            log(f"Piper voice {name} installed in {folder}")
        return True


def _voice(name: str):
    with _load_lock:
        voice = _loaded.get(name)
        if voice is None:
            from piper import PiperVoice

            voice = PiperVoice.load(str(voices_dir() / f"{name}.onnx"))
            _loaded[name] = voice
        return voice


def preload(name: str) -> None:
    _voice(name)


def synthesize(text: str, voice: str) -> bytes:
    """Synthesize ``text`` with an installed voice and return WAV bytes."""
    model = _voice(voice)
    buf = io.BytesIO()
    with _synth_lock, wave.open(buf, "wb") as wav:
        model.synthesize_wav(text, wav)
    data = buf.getvalue()
    if len(data) <= 44:
        raise RuntimeError("Piper produced no audio")
    return data
