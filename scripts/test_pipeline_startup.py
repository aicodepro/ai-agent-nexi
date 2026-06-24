"""Quick pipeline startup test — no mic, no subprocess."""
import os
import sys
import struct
import numpy as np

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

print("=== Pipeline startup test ===")

# 1. Scorer
from engine.audio_wake_pipeline import OpenWakeWordScorer, build_vad, AudioWakePipeline
try:
    scorer = OpenWakeWordScorer(pretrained="hey_nexi")
    print(f"[SCORER] loaded=yes model={scorer.model_name}")
except Exception as e:
    print(f"[SCORER] FAIL: {type(e).__name__}: {e}")
    sys.exit(1)

# 2. VAD
vad = build_vad()
print(f"[VAD] backend={vad.name}")

# 3. Pipeline (no mic)
p = AudioWakePipeline(wake_scorer=scorer, vad=vad, enable_clap=True)
print(f"[PIPE] clap_enabled={p.is_clap_enabled()} running={p.is_running}")

# 4. Test silence frame
silence = struct.pack("<1280h", *([0] * 1280))
r = p.process_frame(silence)
print(f"[FRAME] silence wake={r['wake']} score={r['score']:.4f} source={r['source']}")

# 5. Test noise frame
noise = (np.random.randn(1280) * 500).astype(np.int16).tobytes()
r2 = p.process_frame(noise)
print(f"[FRAME] noise  wake={r2['wake']} score={r2['score']:.4f} source={r2['source']}")

# 6. Test clap frame
clap = np.zeros(1280, dtype=np.int16)
clap[400:500] = 25000
r3 = p.process_frame(clap.tobytes())
print(f"[FRAME] clap   wake={r3['wake']} score={r3['score']:.4f} source={r3['source']} cooldown={r3['cooldown']}")

# 7. Check module-level API
from engine.audio_wake_pipeline import is_pipeline_running, get_last_start_error
print(f"[PIPE] is_running={is_pipeline_running()} last_error={get_last_start_error() or 'none'}")

print()
print("PASS: Pipeline components are functional.")