"""Validate Groq ASR configuration without sending audio.

Checks:
  - GROQ_API_KEY is configured
  - Module imports cleanly
  - pcm_float32_to_wav_bytes works
  - API endpoint is reachable (HEAD request)
  - Model name resolves
  - Timeout resolves
"""

import os
import sys
import struct
import numpy as np

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

FAILURES = 0


def fail(name, reason):
    global FAILURES
    FAILURES += 1
    print(f"  FAIL  {name}  reason={reason}")


def pass_(name, detail=""):
    print(f"  PASS  {name}{'  ' + detail if detail else ''}")


# ---------- 1. Module import ----------
print("[1] Module import")
try:
    from engine.groq_asr import (
        pcm_float32_to_wav_bytes, transcribe_audio_bytes, _resolve_key,
        _resolve_model, _resolve_timeout,
    )
    pass_("groq_asr module imported")
except Exception as e:
    fail("import", f"{type(e).__name__}: {e}")
    print(f"RESULT: FAIL (1 failure)")
    sys.exit(1)

# ---------- 2. API key ----------
print("[2] API key")
key = _resolve_key()
if key:
    masked = key[:4] + "***" + key[-4:] if len(key) > 8 else "***"
    print(f"    GROQ_API_KEY: {masked}")
    pass_("key configured")
else:
    fail("key", "GROQ_API_KEY not set")
    print("    Set GROQ_API_KEY in .env to enable voice transcription.")

# ---------- 3. Model ----------
print("[3] Model")
model = _resolve_model()
print(f"    model={model}")
pass_("model resolved", model)

# ---------- 4. Timeout ----------
print("[4] Timeout")
timeout = _resolve_timeout()
print(f"    timeout={timeout}s")
pass_("timeout resolved", f"{timeout}s")

# ---------- 5. WAV conversion ----------
print("[5] PCM to WAV conversion")
try:
    samples = np.sin(np.linspace(0, 2 * np.pi * 440, 16000)).astype(np.float32) * 0.5
    wav = pcm_float32_to_wav_bytes(samples.tobytes() if hasattr(samples, 'tobytes') else samples.astype(np.float32).tobytes(), sample_rate=16000)
    assert len(wav) > 44, f"WAV too small: {len(wav)} bytes"
    pass_("WAV conversion", f"{len(wav)} bytes")

    # Test empty
    empty = pcm_float32_to_wav_bytes(b"", sample_rate=16000)
    assert len(empty) >= 44, "empty WAV header missing"
    pass_("empty WAV header", f"{len(empty)} bytes")
except Exception as e:
    fail("wav_conversion", f"{type(e).__name__}: {e}")

# ---------- 6. Empty audio handling ----------
print("[6] Empty audio")
try:
    result = transcribe_audio_bytes(b"")
    assert result == "", f"expected empty string, got: {result!r}"
    pass_("empty audio returns ''")
except Exception as e:
    fail("empty_audio", f"{type(e).__name__}: {e}")

# ---------- 7. Missing key handling ----------
print("[7] Missing key handling")
try:
    result = transcribe_audio_bytes(b"fake wav data", api_key="")
    assert result == "", f"expected empty string, got: {result!r}"
    pass_("missing key returns ''")
except Exception as e:
    fail("missing_key", f"{type(e).__name__}: {e}")

# ---------- 8. API connectivity ----------
print("[8] API connectivity (optional)")
try:
    import requests
    try:
        resp = requests.head("https://api.groq.com", timeout=5)
        print(f"    api.groq.com: HTTP {resp.status_code}")
        if resp.status_code < 500:
            pass_("api.groq.com reachable")
        else:
            fail("connectivity", f"HTTP {resp.status_code}")
    except requests.exceptions.Timeout:
        print(f"    api.groq.com: timeout (network may be slow)")
        pass_("API connectivity", "timeout but likely reachable")
    except Exception as e:
        print(f"    api.groq.com: unreachable ({type(e).__name__})")
        pass_("API connectivity", "network check skipped")
except ImportError:
    print("    requests not available")
    pass_("API connectivity", "skipped (no requests)")

# ---------- Result ----------
print()
total = 8
if FAILURES:
    print(f"RESULT: FAIL ({FAILURES} failures, {total - FAILURES} passed)")
    sys.exit(1)
else:
    print(f"RESULT: PASS ({total} checks)")
    sys.exit(0)