"""Quick dependency + import check for the Batch 4 wake pipeline.

Imports `engine.audio_wake_pipeline`, reports which optional deps are
available, and confirms the module-level API surface exists. Does NOT
start the live mic loop (that's a manual run with `python run.py`).
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    print("[SMOKE] dependency probe")
    deps = ("openwakeword", "sounddevice", "silero_vad", "torch", "numpy", "requests")
    for d in deps:
        ok = importlib.util.find_spec(d) is not None
        print(f"[SMOKE]   {d:14s} = {'+' if ok else '-'}")

    try:
        from engine.audio_wake_pipeline import (
            AudioWakePipeline,
            start_audio_wake_pipeline,
            stop_audio_wake_pipeline,
            is_pipeline_running,
            build_vad,
            SAMPLE_RATE,
            FRAME_SAMPLES,
        )
    except Exception as e:
        print(f"[SMOKE] import failed: {type(e).__name__}: {e}")
        return 1

    print(f"[SMOKE] module_loaded sample_rate={SAMPLE_RATE} frame_samples={FRAME_SAMPLES}")
    print(f"[SMOKE] is_pipeline_running={is_pipeline_running()}")

    # Build a pipeline object but do NOT start() (no mic in this smoke).
    pipeline = AudioWakePipeline()
    print(f"[SMOKE] pipeline_built clap_enabled={pipeline.is_clap_enabled()}")
    print("[SMOKE] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
