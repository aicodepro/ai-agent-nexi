"""Phase 2 mic probe: list devices, open default input, print RMS/peak for 10 s."""
import os, sys, time, struct, math
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv()

RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
BLOCK = int(os.getenv("AUDIO_FRAME_SAMPLES", "1280"))
DURATION = 10
DEVICE = os.getenv("AUDIO_INPUT_DEVICE", "").strip() or None
if DEVICE and DEVICE.isdigit():
    DEVICE = int(DEVICE)

import sounddevice as sd, numpy as np

print("[MIC] devices:")
for i, d in enumerate(sd.query_devices()):
    tag = "INPUT " if d["max_input_channels"] > 0 else "      "
    print(f"  {i:3d}  {tag}  {d['name']}")

print(f"\n[MIC] opening device={DEVICE or 'default'} rate={RATE} block={BLOCK}")
print(f"[MIC] recording {DURATION}s — speak or clap to see RMS/peak rise\n")

t0 = time.time()
last_print = 0.0

def callback(indata, frames, ti, status):
    global last_print
    now = time.time()
    if now - last_print < 0.3:
        return
    last_print = now
    pcm = (indata[:, 0] * 32767.0).clip(-32768, 32767).astype(np.int16)
    rms = float(np.sqrt(np.mean(pcm.astype(np.float64)**2)) / 32768.0)
    peak = float(np.max(np.abs(pcm)) / 32768.0)
    elapsed = now - t0
    print(f"  [{elapsed:5.1f}s]  rms={rms:.4f}  peak={peak:.4f}")

try:
    with sd.InputStream(samplerate=RATE, channels=1, blocksize=BLOCK,
                        dtype="float32", callback=callback,
                        device=DEVICE if DEVICE is not None else None):
        time.sleep(DURATION)
except Exception as e:
    print(f"[MIC] error: {e}")
    sys.exit(1)
print("[MIC] done")
