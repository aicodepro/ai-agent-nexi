"""Phase 3 openWakeWord score probe: print model score + RMS every ~250 ms for 30 s."""
import os, sys, time, queue
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv()

RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
BLOCK = int(os.getenv("AUDIO_FRAME_SAMPLES", "1280"))
DURATION = 30
MODEL_PATH = (os.getenv("OPENWAKEWORD_MODEL_PATH", "") or "").strip()
PRETRAINED = (os.getenv("OPENWAKEWORD_PRETRAINED_MODELS", "hey_jarvis") or "hey_jarvis").strip()
THRESHOLD = float(os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.5"))
DEVICE = os.getenv("AUDIO_INPUT_DEVICE", "").strip() or None
if DEVICE and DEVICE.isdigit():
    DEVICE = int(DEVICE)

import sounddevice as sd, numpy as np
from openwakeword.model import Model as OWWModel

# Load model
if MODEL_PATH and os.path.exists(MODEL_PATH):
    model = OWWModel(wakeword_models=[MODEL_PATH], inference_framework="onnx")
    print(f"[OWW] loaded custom model: {MODEL_PATH}")
else:
    names = [n.strip() for n in PRETRAINED.split(",") if n.strip()]
    model = OWWModel(wakeword_models=names, inference_framework="onnx")
    print(f"[OWW] loaded pretrained: {names}")

print(f"[OWW] models: {list(model.models.keys())}")
print(f"[OWW] threshold={THRESHOLD} device={DEVICE or 'default'}")
print(f"[OWW] speak the wake phrase now (running {DURATION}s)...\n")

q = queue.Queue(maxsize=64)
def callback(indata, frames, ti, status):
    pcm = (indata[:, 0] * 32767.0).clip(-32768, 32767).astype(np.int16)
    try:
        q.put_nowait(pcm)
    except queue.Full:
        pass

t0 = time.time()
last_print = 0.0
max_score = 0.0

try:
    with sd.InputStream(samplerate=RATE, channels=1, blocksize=BLOCK,
                        dtype="float32", callback=callback,
                        device=DEVICE if DEVICE is not None else None):
        while time.time() - t0 < DURATION:
            try:
                pcm = q.get(timeout=0.3)
            except queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(pcm.astype(np.float64)**2)) / 32768.0)
            peak = float(np.max(np.abs(pcm)) / 32768.0)
            preds = model.predict(pcm)
            score = max(preds.values()) if isinstance(preds, dict) else float(preds)
            if score > max_score:
                max_score = score
            now = time.time()
            if now - last_print >= 0.25 or score >= THRESHOLD:
                elapsed = now - t0
                hit = "WAKE" if score >= THRESHOLD else ""
                names = preds if isinstance(preds, dict) else {"model": preds}
                print(f"  [{elapsed:5.1f}s]  rms={rms:.4f}  peak={peak:.4f}  score={score:.4f}  {hit}  {names}")
                last_print = now
except KeyboardInterrupt:
    pass
except Exception as e:
    print(f"[OWW] error: {e}")
    sys.exit(1)

print(f"\n[OWW] max_score_seen={max_score:.4f}  threshold={THRESHOLD}")
if max_score >= THRESHOLD:
    print("[OWW] RESULT: wake phrase WAS detected at least once")
else:
    print("[OWW] RESULT: wake phrase was NOT detected — try speaking closer to mic or lower threshold")
