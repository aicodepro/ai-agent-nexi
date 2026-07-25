# Stage 1 — Dependency Report

**Environment:** Windows 11, Python 3.11.15, project venv `E:\ai-agnet-nexi\.venv`

---

## 1. Undeclared runtime dependencies — FIXED

Seven modules were imported by runtime code but absent from `requirements.txt`.
A fresh clone could install "successfully" and then fail at startup, because
the wake pipeline and vision subsystems import these directly.

| Package | Imported as | Used by | Was declared |
| --- | --- | --- | --- |
| `openwakeword` | `openwakeword` | `engine/audio_wake_pipeline.py`, `hotword_engine_manager.py` | no |
| `sounddevice` | `sounddevice` | mic capture in `audio_wake_pipeline.py` | no |
| `scipy` | `scipy` | audio processing | no |
| `opencv-contrib-python` | `cv2` | `engine/camera_control/*`, face auth | no |
| `mediapipe` | `mediapipe` | hand/eye tracking | no |
| `uiautomation` | `uiautomation` | `engine/computer_use.py` (semantic desktop control) | no |
| `defusedxml` | `defusedxml` | safe XML parsing | no |

All seven are now declared. `uiautomation` and `pywin32` are guarded with
`sys_platform == "win32"`.

> Discovered during this session: `opencv` and `mediapipe` were **absent from
> the venv entirely** at one point, which made 30 camera/vision tests fail. The
> failures were an environment gap, not a code defect — they pass once the
> declared dependencies are installed.

## 2. Dependency groups — ADDED

`pyproject.toml` now defines installable extras so a clean checkout can install
exactly what a given lane needs:

| Group | Purpose | Key packages |
| --- | --- | --- |
| *(core)* | start, route, respond | eel, python-dotenv, requests, numpy, psutil, defusedxml |
| `voice` | wake / VAD / ASR / TTS | openwakeword, sounddevice, scipy, edge-tts, pyttsx3, pyaudio |
| `windows` | desktop control | pywin32, uiautomation, comtypes, pyautogui, keyboard, pynput |
| `browser` | browser control + rendered search | playwright, crawl4ai |
| `vision` | camera / hand / eye / face | opencv-contrib-python, mediapipe, pillow |
| `brain` | semantic routing | sentence-transformers |
| `training` | wake-model training only | torch, scipy |
| `test` / `dev` | CI | pytest, ruff |
| `all` | full Windows assistant | voice + windows + browser + vision + brain |

Headless CI can install core + `test` only, which is what makes a headless lane
possible at all.

## 3. TTS provider dependencies

`edge-tts` was added this session. It is the primary voice provider: free,
keyless, no terms acceptance, ~1 s synthesis, and genuinely natural — replacing
the robotic SAPI5 fallback that was previously reached on every response.

Groq TTS remains as a secondary provider. Its `canopylabs/orpheus-v1-english`
model returns `requires terms acceptance` until an org admin accepts in the
Groq console → **BLOCKED**, documented, not worked around.

## 4. Remaining gaps — NOT FIXED

| Gap | Impact | Status |
| --- | --- | --- |
| **No version pins / lockfile** | Two installs can resolve differently; builds are not reproducible | OPEN |
| **`openai>=0.28,<1`** | Pinned to the legacy 0.x API | OPEN |
| **Clean-venv install not executed** | Groups are declared but unproven | OPEN (B-03) |
| **No `pip-audit` / dependency provenance** | Vulnerable or unlicensed transitive deps would go unnoticed | OPEN |

Pinning should be done as a deliberate step (generate a lockfile from a clean
resolve, then verify the full suite against it) rather than guessed here — a
wrong pin silently breaks the runtime.

## 5. Verification performed

```
pyproject.toml parses               -> project nexi-access 1.0.0, 8 core deps, 9 groups
pytest collection after change      -> 3428 tests collected, no error
all 7 added deps import in venv     -> confirmed
```

Not performed (see B-03): clean clone → empty venv → `pip install .[all]` →
full suite.
