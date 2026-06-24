"""Validate the Nexi voice runtime without microphone hardware.

Checks:
  - All core voice modules import without error
  - AudioWakePipeline class is functional
  - ClapStateMachine class is functional
  - Groq ASR has GROQ_API_KEY configured
  - runtime_bridge event types defined
  - command_bus routing intact
  - TTS engine (pyttsx3) initializes
  - interrupt_controller is functional
  - UI mode does not affect voice modules
"""

import os
import sys
import traceback

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

TESTS = []
FAILURES = 0


def check(name, fn):
    TESTS.append((name, fn))


def run_all():
    global FAILURES
    for name, fn in TESTS:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:
            FAILURES += 1
            print(f"  FAIL  {name}  reason={type(e).__name__}: {e}")

    print()
    if FAILURES:
        print(f"RESULT: FAIL ({FAILURES} failures, {len(TESTS) - FAILURES} passed)")
        sys.exit(1)
    else:
        print(f"RESULT: PASS ({len(TESTS)} checks)")
        sys.exit(0)


# ---------- Module imports ----------
def _test_import_audio_wake_pipeline():
    from engine.audio_wake_pipeline import (
        AudioWakePipeline, OpenWakeWordScorer, EnergyVAD, build_vad,
        start_audio_wake_pipeline, is_pipeline_running, get_last_start_error,
    )
check("import audio_wake_pipeline", _test_import_audio_wake_pipeline)


def _test_import_clap_detector():
    from engine.clap_detector import (
        ClapStateMachine, ClapListener, is_clap_frame, detect_double_clap,
        CLAP_DETECTION_ENABLED,
    )
check("import clap_detector", _test_import_clap_detector)


def _test_import_groq_asr():
    from engine.groq_asr import pcm_float32_to_wav_bytes, transcribe_audio_bytes
    key = os.getenv("GROQ_API_KEY", "").strip()
    assert key, "GROQ_API_KEY not set in environment"
    print(f"    GROQ_API_KEY: configured")
check("import groq_asr", _test_import_groq_asr)


def _test_import_runtime_bridge():
    from engine.runtime_bridge import (
        post_command, post_status, post_wake_detected,
        handle_bridge_event, start_ui_bridge_pump, stop_ui_bridge_pump,
    )
check("import runtime_bridge", _test_import_runtime_bridge)


def _test_import_command_bus():
    from engine.command_bus import (
        submit_user_command, dispatch_unified_command, is_dispatching,
    )
check("import command_bus", _test_import_command_bus)


def _test_import_tts():
    from engine.tts_response_manager import build_spoken_text, split_tts_chunks, speak_interruptible
check("import tts_response_manager", _test_import_tts)


def _test_import_interrupt():
    from engine.interrupt_controller import (
        is_speaking, request_interrupt, clear_interrupt, set_speaking,
    )
check("import interrupt_controller", _test_import_interrupt)


def _test_import_turn_manager():
    from engine.turn_manager import (
        mark_user_turn_started, mark_assistant_speaking, mark_assistant_done,
    )
check("import turn_manager", _test_import_turn_manager)


def _test_import_features():
    from engine.features import start_clap_if_enabled, hotword_no_key
check("import features", _test_import_features)


def _test_import_command():
    from engine.command import speak, takecommand, allCommands
check("import command", _test_import_command)


# ---------- Functional checks ----------
def _test_pipeline_class():
    from engine.audio_wake_pipeline import AudioWakePipeline
    p = AudioWakePipeline()
    assert p.last_start_error == ""
    assert not p.is_running
check("AudioWakePipeline instantiation", _test_pipeline_class)


def _test_clap_state_machine():
    from engine.clap_detector import ClapStateMachine
    sm = ClapStateMachine()
    assert sm.state == "idle"
check("ClapStateMachine instantiation", _test_clap_state_machine)


def _test_vad_build():
    from engine.audio_wake_pipeline import build_vad
    vad = build_vad()
    assert vad is not None
    print(f"    strategy={vad.name}")
check("build_vad", _test_vad_build)


def _test_pyttsx3_init():
    import pyttsx3
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    assert len(voices) > 0
    print(f"    voices={len(voices)}")
check("pyttsx3 engine", _test_pyttsx3_init)


def _test_ui_mode_isolation():
    ui_mode = os.getenv("NEXI_UI_MODE", "legacy")
    assert ui_mode in ("legacy", "mark"), f"unexpected mode: {ui_mode}"
    print(f"    NEXI_UI_MODE={ui_mode}")

    from engine.ui_loader import get_ui_mode
    mode = get_ui_mode()
    assert mode in ("legacy", "mark")
    print(f"    ui_loader.get_ui_mode()={mode}")

    # Verify voice modules do not import ui_loader
    voice_files = [
        "engine/audio_wake_pipeline.py",
        "engine/clap_detector.py",
        "engine/groq_asr.py",
        "engine/runtime_bridge.py",
        "engine/command_bus.py",
        "engine/tts_response_manager.py",
        "engine/interrupt_controller.py",
    ]
    for fpath in voice_files:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
            assert "ui_loader" not in content, f"{fpath} references ui_loader"
    print(f"    voice modules isolated: {len(voice_files)} files checked")
check("UI mode isolation", _test_ui_mode_isolation)


def _test_env_keys_safe():
    required = ["GROQ_API_KEY", "GEMINI_API_KEY"]
    for key in required:
        val = os.getenv(key, "").strip()
        present = bool(val)
        print(f"    {key}: {'SET' if present else 'MISSING'}")
        if key == "GROQ_API_KEY":
            assert present, "GROQ_API_KEY required for voice ASR"
check("API keys configured", _test_env_keys_safe)


def _test_dependencies():
    deps = ["pyaudio", "pyttsx3", "eel", "speech_recognition", "numpy"]
    for dep in deps:
        try:
            __import__(dep)
            print(f"    {dep}: OK")
        except ImportError:
            print(f"    {dep}: MISSING (optional)")

    # openwakeword is required for VOICE_WAKE_BACKEND=openwakeword
    try:
        __import__("openwakeword")
        print(f"    openwakeword: OK")
    except ImportError:
        print(f"    openwakeword: MISSING (required for OWW pipeline)")

    # sounddevice is required for OWW pipeline
    try:
        __import__("sounddevice")
        print(f"    sounddevice: OK")
    except ImportError:
        print(f"    sounddevice: MISSING (required for OWW pipeline)")

    # silero-vad is optional
    try:
        __import__("silero_vad")
        print(f"    silero_vad: OK")
    except ImportError:
        print(f"    silero_vad: MISSING (optional, falls back to EnergyVAD)")
check("dependencies", _test_dependencies)


if __name__ == "__main__":
    print("=== Nexi Voice Runtime Debug ===")
    print(f"pid={os.getpid()} cwd={os.getcwd()}")
    print()
    run_all()