"""Full runtime startup trace — mimics run.py but prints diagnostics.

Shows exactly what happens when run.py starts, including:
  - Env vars loaded
  - Which wake backend is selected
  - Whether OWW pipeline starts
  - Whether clap manager initializes
  - Whether mic stream can open

Usage: python scripts/debug_full_runtime.py
"""

import os
import sys
import time

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

print("=== NEXI Full Runtime Startup Trace ===")
print(f"cwd={os.getcwd()}")
print(f"pid={os.getpid()}")
print()

# ---- Step 1: Env inspection ----
print("[1] Environment variables (keys only, no values)")
relevant = [
    "VOICE_WAKE_BACKEND", "OPENWAKEWORD_ENABLED", "OPENWAKEWORD_PRETRAINED_MODELS",
    "OPENWAKEWORD_SCORE_THRESHOLD", "OPENWAKEWORD_CONSECUTIVE_HITS",
    "DISABLE_LEGACY_HOTWORD_FALLBACK", "WAKE_DEBUG",
    "CLAP_DETECTION_ENABLED", "NEXI_CLAP_PRIMARY", "NEXI_CLAP_FALLBACK",
    "NEXI_CLAP_DEBUG", "NEXI_CLAP_COOLDOWN_MS",
    "GROQ_API_KEY", "GEMINI_API_KEY",
    "AUDIO_INPUT_DEVICE", "AUDIO_SAMPLE_RATE", "AUDIO_CHANNELS",
    "VAD_BACKEND", "NEXI_UI_MODE",
]
for k in relevant:
    v = os.getenv(k, "")
    if "KEY" in k:
        print(f"  {k}: {'SET' if v else 'MISSING'}")
    else:
        print(f"  {k}: {v!r}")
print()

# ---- Step 2: Backend selection (mirrors run.py:listenHotword) ----
print("[2] Backend selection (run.py:listenHotword)")
backend = (os.getenv("VOICE_WAKE_BACKEND", "") or "").lower().strip()
legacy_fallback_disabled = (os.getenv("DISABLE_LEGACY_HOTWORD_FALLBACK", "false") or "false").lower() == "true"
print(f"  VOICE_WAKE_BACKEND: {backend!r}")

if backend == "openwakeword":
    print("  Path: openwakeword pipeline")
else:
    print(f"  Path: LEGACY (SpeechRecognition + features.hotword_no_key)")
print(f"  Legacy fallback: {'DISABLED' if legacy_fallback_disabled else 'ENABLED'}")
print()

# ---- Step 3: Try to import and start OWW pipeline ----
print("[3] OpenWakeWord pipeline import")
if backend == "openwakeword":
    try:
        from engine.audio_wake_pipeline import (
            AudioWakePipeline, OpenWakeWordScorer, build_vad,
            start_audio_wake_pipeline, is_pipeline_running, get_last_start_error,
        )
        print("  Import: OK")

        # Build scorer
        print("  Building OpenWakeWordScorer...")
        scorer = OpenWakeWordScorer(pretrained=os.getenv("OPENWAKEWORD_PRETRAINED_MODELS", "hey_nexi"))
        print(f"  Scorer: model={scorer.model_name}")

        # Build VAD
        vad = build_vad()
        print(f"  VAD: backend={vad.name}")

        # Create pipeline (no mic yet)
        p = AudioWakePipeline(wake_scorer=scorer, vad=vad, enable_clap=True)
        print(f"  Pipeline: created clap_enabled={p.is_clap_enabled()}")

        # Test scoring
        import struct
        import numpy as np
        silence = struct.pack("<1280h", *([0]*1280))
        noise = (np.random.randn(1280)*500).astype(np.int16).tobytes()
        r_sil = p.process_frame(silence)
        r_noise = p.process_frame(noise)
        print(f"  Silence score: {r_sil['score']:.4f} wake={r_sil['wake']} source={r_sil['source']}")
        print(f"  Noise score: {r_noise['score']:.4f} wake={r_noise['wake']} source={r_noise['source']}")

        # Test OWW threshold vs actual scores
        oww_threshold = float(os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.5"))
        oww_hits = int(os.getenv("OPENWAKEWORD_CONSECUTIVE_HITS", "2"))
        print(f"  OWW config: threshold={oww_threshold} consecutive_hits={oww_hits}")
        print(f"  NOTE: Model needs {oww_hits} consecutive frames >= {oww_threshold} to trigger")

        # Check if model path is correct
        import openwakeword
        oww_dir = os.path.dirname(openwakeword.__file__)
        models_dir = os.path.join(oww_dir, "resources", "models")
        pretrained_name = os.getenv("OPENWAKEWORD_PRETRAINED_MODELS", "hey_nexi")
        model_file = f"{pretrained_name}_v0.1.onnx"
        model_path = os.path.join(models_dir, model_file)
        if os.path.exists(model_path):
            print(f"  Model file: EXISTS ({os.path.getsize(model_path)} bytes)")
        else:
            print(f"  Model file: MISSING ({model_path})")
            alt = [f for f in os.listdir(models_dir) if f.startswith(pretrained_name)]
            print(f"  Alternatives: {alt}")

    except Exception as e:
        import traceback
        print(f"  FAIL: {type(e).__name__}: {e}")
        traceback.print_exc()
else:
    print("  Skipped (not openwakeword backend)")
print()

# ---- Step 4: Try clap backend manager ----
print("[4] Clap backend manager")
try:
    from engine.clap_backend_manager import ClapBackendManager
    mgr = ClapBackendManager(cooldown_ms=1500)
    status = mgr.get_status()
    print(f"  Primary: {status['primary']} ready={status['primary_ready']}")
    print(f"  Fallback: {status['fallback']} ready={status['fallback_ready']}")

    # Process a test frame
    import struct
    silence = struct.pack("<1280h", *([0]*1280))
    r = mgr.process_audio_chunk(silence)
    print(f"  Silence result: wake={r['wake']} backend_used={r.get('backend_used','?')}")

    import numpy as np
    clap = np.zeros(1280, dtype=np.int16)
    clap[400:500] = 25000
    r2 = mgr.process_audio_chunk(clap.tobytes())
    print(f"  Clap frame: wake={r2['wake']} backend_used={r2.get('backend_used','?')} clap={r2.get('clap')}")

    # Tzur debug
    if status["primary_ready"]:
        snap = mgr.get_debug_snapshot()
        if "primary_stats" in snap:
            ps = snap["primary_stats"]
            print(f"  Tzur stats: ema={ps.get('ema_threshold',0):.6f} singles={ps.get('detected_single',0)} doubles={ps.get('detected_double',0)}")
except Exception as e:
    import traceback
    print(f"  FAIL: {type(e).__name__}: {e}")
    traceback.print_exc()
print()

# ---- Step 5: Test mic stream opening ----
print("[5] Microphone stream test")
try:
    import sounddevice as sd

    AUDIO_INPUT_DEVICE = os.getenv("AUDIO_INPUT_DEVICE", "")
    device = None
    if AUDIO_INPUT_DEVICE:
        device = int(AUDIO_INPUT_DEVICE) if AUDIO_INPUT_DEVICE.isdigit() else AUDIO_INPUT_DEVICE

    dev_info = sd.query_devices(device, "input") if device is not None else sd.query_devices(kind="input")
    print(f"  Device: {dev_info['name'][:50]} (idx={dev_info['index']})")
    print(f"  Native rate: {int(dev_info['default_samplerate'])} ch_in: {int(dev_info['max_input_channels'])}")

    SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    CHANNELS = int(os.getenv("AUDIO_CHANNELS", "1"))
    FRAME_SAMPLES = int(os.getenv("AUDIO_FRAME_SAMPLES", "1280"))
    print(f"  Opening: rate={SAMPLE_RATE} ch={CHANNELS} blocksize={FRAME_SAMPLES}")

    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                           blocksize=FRAME_SAMPLES, dtype="float32")
    stream.start()
    print("  Stream: STARTED")

    # Read a few frames
    import numpy as np
    for i in range(5):
        data, overflowed = stream.read(FRAME_SAMPLES)
        rms = float(np.sqrt(np.mean(data ** 2)))
        if i == 0:
            print(f"  Frame 0: RMS={rms:.6f}")
    print(f"  Final RMS: {rms:.6f}")

    stream.stop()
    stream.close()
    print("  Stream: CLOSED OK")

except Exception as e:
    import traceback
    print(f"  FAIL: {type(e).__name__}: {e}")
    traceback.print_exc()
print()

# ---- Step 6: Hotword helper check ----
print("[6] Hotword helper")
try:
    from engine.hotword_helper import set_hotword_awake, is_hotword_awake
    print(f"  hotword_helper: OK, awake={is_hotword_awake()}")
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
print()

# ---- Summary ----
print("=== DIAGNOSIS COMPLETE ===")
print()
print("If 'Hey Nexi' does not respond:")
print("  1. Verify mic is not muted in Windows settings")
print("  2. Verify default input device is Microphone Array")
print("  3. Try lowering threshold: OPENWAKEWORD_SCORE_THRESHOLD=0.3")
print("  4. Try reducing hits: OPENWAKEWORD_CONSECUTIVE_HITS=1")
print("  5. Enable debug: WAKE_DEBUG=true")
print()
print("If double clap does not respond:")
print("  1. Verify CLAP_DETECTION_ENABLED=true in .env")
print("  2. Run: python scripts/debug_clap_calibration.py")
print("  3. Try: NEXI_CLAP_DEBUG=true")
print()
print("If audio process does not start at all:")
print("  1. Verify running python run.py, NOT python main.py")
print("  2. Check sounddevice is installed: pip install sounddevice")