# Third-Party Notices

Twitch TTS Engine (MIT License) bundles and depends on the following
open-source components. Their licenses are reproduced or linked below in
accordance with their terms.

## Runtime dependencies

| Component | License | Used for |
|---|---|---|
| [edge-tts](https://github.com/rany2/edge-tts) | **LGPL-3.0** (except `src/edge_tts/srt_composer.py`, MIT) | Neural speech synthesis |
| [pygame-ce](https://github.com/pygame-community/pygame-ce) | **LGPL-2.1** | Host-audio playback |
| [aiohttp](https://github.com/aio-libs/aiohttp) | Apache-2.0 / MIT (dual) | Async HTTP in edge-tts |
| [pystray](https://github.com/moses-palmer/pystray) | MIT | System tray icon |
| [Pillow](https://github.com/python-pillow/Pillow) | HPND (MIT-like) | Tray icon drawing |
| [miniaudio](https://github.com/irmen/miniaudio) | MIT (public domain core) | MP3 decoding for host audio |
| [piper-tts](https://github.com/OHF-Voice/piper1-gpl) | **GPL-3.0-or-later** (bundles espeak-ng data, GPL-3.0) | Offline neural speech synthesis |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | MIT | Runs Piper voice models |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause | Audio arrays in Piper |

Piper voice models are downloaded at runtime, not bundled. Each has its own
dataset license (see its `MODEL_CARD` on Hugging Face); the default
`en_US-joe-medium` is CC0.

## GPL notice (Windows exe)

The `twitchTTS.exe` release binary bundles piper-tts, which is licensed
under the GNU GPL v3 or later. The binary as a whole is therefore
distributed under the terms of the GPL-3.0; this project's own source code
remains MIT-licensed. The complete corresponding source is this repository
plus the unmodified upstream packages listed above. Running from source
without piper-tts installed involves no GPL code.

- GPL-3.0: <https://www.gnu.org/licenses/gpl-3.0.txt>

## LGPL notices

**edge-tts** and **pygame-ce** are licensed under the GNU Lesser General
Public License. You can use, study, share and modify Twitch TTS Engine
under the MIT License, and the LGPL components remain licensed under the
LGPL. In particular:

- The full license texts are available at:
  - LGPL-3.0: <https://www.gnu.org/licenses/lgpl-3.0.txt>
  - LGPL-2.1: <https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt>
- Source code for the LGPL components is available from their upstream
  repositories listed above, and this project's source is public at
  <https://github.com/vhsgreed/twitchTTS>, satisfying the requirement to
  permit relinking/replacing the libraries.
- No modifications are made to the LGPL components; they are used
  unmodified via their public APIs.

## MIT license (this project)

```text
MIT License

Copyright (c) 2026 karlsune

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
