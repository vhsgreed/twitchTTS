"""Keep the edge-tts requirement in step with PyPI.

Used by .github/workflows/edge-tts-watch.yml:
  check        print `pinned=`, `latest=`, `outdated=` for $GITHUB_OUTPUT
  synth        synthesize a short line with the installed edge-tts (exit 1 on failure)
  bump X.Y.Z   rewrite `edge-tts>=...` in requirements*.txt and README.md,
               and note it under [Unreleased] in CHANGELOG.md
"""
import asyncio
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
PIN_FILES = ["requirements.txt", "requirements-linux.txt", "README.md"]
PIN_RE = re.compile(r"edge-tts>=([0-9][0-9.]*[0-9])")
BOM = "\ufeff"


def read(path):
    text = path.read_text(encoding="utf-8")
    return text.startswith(BOM), text.lstrip(BOM)


def write(path, had_bom, text):
    path.write_text((BOM if had_bom else "") + text, encoding="utf-8", newline="")


def vkey(v):
    return tuple(int(p) for p in v.split("."))


def pinned():
    _, text = read(ROOT / "requirements.txt")
    m = PIN_RE.search(text)
    if not m:
        sys.exit("requirements.txt has no edge-tts>= line")
    return m.group(1)


def latest():
    with urllib.request.urlopen("https://pypi.org/pypi/edge-tts/json", timeout=30) as r:
        return json.load(r)["info"]["version"]


def check():
    p, l = pinned(), latest()
    print(f"pinned={p}")
    print(f"latest={l}")
    print(f"outdated={'true' if vkey(l) > vkey(p) else 'false'}")


def synth():
    import edge_tts

    async def run():
        size = 0
        async for chunk in edge_tts.Communicate(
            "edge tts health check", "en-US-AvaMultilingualNeural"
        ).stream():
            if chunk["type"] == "audio":
                size += len(chunk["data"])
        return size

    try:
        size = asyncio.run(run())
    except Exception as e:  # noqa: BLE001 - any failure is the signal
        sys.exit(f"edge-tts {edge_tts.__version__} synthesis FAILED: {e}")
    if size < 1000:
        sys.exit(f"edge-tts {edge_tts.__version__} returned only {size} audio bytes")
    print(f"edge-tts {edge_tts.__version__} synthesis OK ({size} bytes)")


def bump(new):
    for name in PIN_FILES:
        path = ROOT / name
        bom, text = read(path)
        out, n = PIN_RE.subn(f"edge-tts>={new}", text)
        if n == 0:
            sys.exit(f"{name}: no edge-tts>= pin found")
        write(path, bom, out)
        print(f"{name}: {n} pin(s) -> {new}")

    path = ROOT / "CHANGELOG.md"
    bom, text = read(path)
    start = text.index("## [Unreleased]")
    end = text.find("\n## [", start + 1)
    end = len(text) if end == -1 else end
    section = text[start:end]
    bullet = f"- Require `edge-tts>={new}` (latest release; older versions can be\n  rejected by Microsoft's speech service)."
    old = re.compile(r"- Require `edge-tts>=[^`]+` \(latest release;[^\n]*\n  rejected by Microsoft's speech service\)\.")
    if old.search(section):
        section = old.sub(bullet, section)
    elif "### Changed\n\n" in section:
        section = section.replace("### Changed\n\n", f"### Changed\n\n{bullet}\n", 1)
    else:
        section = section.rstrip("\n") + f"\n\n### Changed\n\n{bullet}\n"
    section = section.rstrip("\n") + "\n"
    write(path, bom, text[:start] + section + text[end:])
    print("CHANGELOG.md: [Unreleased] updated")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check":
        check()
    elif cmd == "synth":
        synth()
    elif cmd == "bump" and len(sys.argv) == 3:
        bump(sys.argv[2])
    else:
        sys.exit(__doc__)
