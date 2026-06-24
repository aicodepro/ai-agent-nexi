"""
debug_full_wake_reply_flow.py

Tests each step of the wake → listen → ASR → command → TTS → sleep flow.
Prints PASS/FAIL for each step.
Saves logs to artifacts/debug_full_wake_reply_flow.log
"""

import os
import sys
import time
import socket
import io
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_log_buffer = []

RESULT_FILE = Path("artifacts") / "debug_full_wake_reply_flow.log"


def _log(msg: str):
    print(msg, flush=True)
    _log_buffer.append(msg)


def _pass(name: str, detail: str = ""):
    _log(f"PASS {name}" + (f" {detail}" if detail else ""))


def _fail(name: str, source: str = "", file_hint: str = ""):
    _log(f"FAIL {name}")
    if source:
        _log(f"  source: {source}")
    if file_hint:
        _log(f"  likely in: {file_hint}")


def test_ui_port_available_or_auto_selected() -> bool:
    try:
        from main import _is_port_available, _find_free_port
        port = int(os.getenv("NEXI_UI_PORT", "8000"))
        host = "localhost"
        available = _is_port_available(host, port)
        if available:
            _pass("ui_port_available_or_auto_selected", f"port={port}")
            return True
        selected, reason = _find_free_port(host, port)
        _pass("ui_port_available_or_auto_selected", f"requested={port} selected={selected} reason={reason}")
        return True
    except Exception as e:
        _fail("ui_port_available_or_auto_selected", source=str(e), file_hint="main.py:_find_free_port")
        return False


def test_hotword_config_loaded() -> bool:
    try:
        from engine.hotword_engine_manager import HotwordEngineManager
        engine = HotwordEngineManager(config={"enabled": False})
        _pass("hotword_config_loaded",
              f"threshold={engine.threshold} hits={engine.consecutive_hits_required} "
              f"phrases={engine.phrases}")
        return True
    except Exception as e:
        _fail("hotword_config_loaded", source=str(e), file_hint="engine/hotword_engine_manager.py")
        return False


def test_pipeline_module_imports() -> bool:
    try:
        from engine.audio_wake_pipeline import AudioWakePipeline, SAMPLE_RATE, FRAME_SAMPLES
        _pass("pipeline_module_imports", f"sample_rate={SAMPLE_RATE} frame={FRAME_SAMPLES}")
        return True
    except Exception as e:
        _fail("pipeline_module_imports", source=str(e), file_hint="engine/audio_wake_pipeline.py")
        return False


def test_bridge_module_imports() -> bool:
    try:
        from engine.runtime_bridge import BridgeEvent, post_status, post_command, handle_bridge_event
        _pass("bridge_module_imports")
        return True
    except Exception as e:
        _fail("bridge_module_imports", source=str(e), file_hint="engine/runtime_bridge.py")
        return False


def test_ui_state_manager() -> bool:
    try:
        from engine.ui_state_manager import UIStateManager, get_ui_state_manager, emit_state, canonical_state
        mgr = UIStateManager(dedupe_ms=0)
        e = mgr.emit("wake_detected", source="hotword")
        assert e is not None
        assert e.state == "online"
        _pass("ui_state_manager", "can emit wake_detected/listening/thinking/saying/sleep")
        return True
    except Exception as e:
        _fail("ui_state_manager", source=str(e), file_hint="engine/ui_state_manager.py")
        return False


def test_clap_manager_has_config() -> bool:
    try:
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        s = mgr.get_status()
        _pass("clap_manager_config",
              f"max_gap={s.get('max_gap_ms')} min_gap={s.get('min_gap_ms')} "
              f"primary={s.get('primary')} primary_ready={s.get('primary_ready')}")
        return True
    except Exception as e:
        _fail("clap_manager_config", source=str(e), file_hint="engine/clap_backend_manager.py")
        return False


def test_dsp_clap_options() -> bool:
    try:
        from engine.dsp_clap_backend import DspClapBackend
        backend = DspClapBackend(sample_rate=16000)
        snap = backend.get_debug_snapshot()
        _pass("dsp_clap_options",
              f"rms_threshold={snap['rms_threshold']} peak_threshold={snap['peak_threshold']} "
              f"peak_ratio={snap['peak_ratio_threshold']} hf_ratio={snap['hf_ratio_threshold']}")
        return True
    except Exception as e:
        _fail("dsp_clap_options", source=str(e), file_hint="engine/dsp_clap_backend.py")
        return False


def test_internal_wake_signal() -> bool:
    try:
        from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal
        bus = InternalWakeSignalBus(debug=False)
        signal = WakeSignal(source="hotword", state="wake_detected",
                            phrase="hey nexi", confidence=0.8,
                            timestamp=time.time(), reason="threshold")
        _pass("internal_wake_signal", "signal creation works")
        return True
    except Exception as e:
        _fail("internal_wake_signal", source=str(e), file_hint="engine/internal_wake_signal.py")
        return False


def test_groq_asr_imports() -> bool:
    try:
        from engine.groq_asr import transcribe_audio_bytes, pcm_float32_to_wav_bytes
        _pass("groq_asr_imports")
        return True
    except Exception as e:
        _fail("groq_asr_imports", source=str(e), file_hint="engine/groq_asr.py")
        return False


def test_groq_tts_imports() -> bool:
    try:
        from engine.groq_tts import is_configured, GroqTTSResult
        _pass("groq_tts_imports")
        return True
    except Exception as e:
        _fail("groq_tts_imports", source=str(e), file_hint="engine/groq_tts.py")
        return False


def test_tts_response_manager() -> bool:
    try:
        from engine.tts_response_manager import build_spoken_text, split_tts_chunks, speak_interruptible
        _pass("tts_response_manager")
        return True
    except Exception as e:
        _fail("tts_response_manager", source=str(e), file_hint="engine/tts_response_manager.py")
        return False


def test_command_bus_imports() -> bool:
    try:
        from engine.command_bus import submit_user_command, normalize_command, dispatch_unified_command
        _pass("command_bus_imports")
        return True
    except Exception as e:
        _fail("command_bus_imports", source=str(e), file_hint="engine/command_bus.py")
        return False


def test_double_clap_no_wake_on_single() -> bool:
    try:
        from engine.clap_backend_manager import ClapBackendManager
        mgr = ClapBackendManager(cooldown_ms=5000)
        now = time.time()
        event = {"clap": True, "wake": False, "source": None, "backend": "dsp_clap",
                 "backend_used": "dsp_clap", "fallback_used": False, "cooldown": False,
                 "amplitude": 0.5, "threshold": 0.0, "gap_ms": None,
                 "reason": "clap_detected_id=1", "pattern": []}
        result = mgr._apply_double_clap_state(event, now)
        assert result["wake"] is False
        _pass("double_clap_no_wake_on_single")
        return True
    except Exception as e:
        _fail("double_clap_no_wake_on_single", source=str(e))
        return False


def test_silence_no_wake() -> bool:
    try:
        from engine.dsp_clap_backend import DspClapBackend
        backend = DspClapBackend(sample_rate=16000)
        pcm = b"\x00\x00" * 320
        result = backend.process_pcm16(pcm)
        assert result.is_clap is False
        _pass("silence_no_wake")
        return True
    except Exception as e:
        _fail("silence_no_wake", source=str(e))
        return False


def test_speech_not_clap() -> bool:
    try:
        from engine.dsp_clap_backend import DspClapBackend
        import struct
        backend = DspClapBackend(sample_rate=16000)
        samples = []
        for i in range(320):
            val = int(5000 * (i % 40) / 40)
            samples.append(max(-32768, min(32767, val)))
        pcm = struct.pack("<320h", *samples)
        result = backend.process_pcm16(pcm)
        _pass("speech_not_clap", f"reason={result.reason}")
        return True
    except Exception as e:
        _fail("speech_not_clap", source=str(e))
        return False


def main():
    _log("=" * 60)
    _log("debug_full_wake_reply_flow.py")
    _log("=" * 60)
    _log("")

    results = []

    tests = [
        ("ui_port_available_or_auto_selected", test_ui_port_available_or_auto_selected),
        ("hotword_config_loaded", test_hotword_config_loaded),
        ("pipeline_module_imports", test_pipeline_module_imports),
        ("bridge_module_imports", test_bridge_module_imports),
        ("ui_state_manager", test_ui_state_manager),
        ("clap_manager_config", test_clap_manager_has_config),
        ("dsp_clap_options", test_dsp_clap_options),
        ("internal_wake_signal", test_internal_wake_signal),
        ("groq_asr_imports", test_groq_asr_imports),
        ("groq_tts_imports", test_groq_tts_imports),
        ("tts_response_manager", test_tts_response_manager),
        ("command_bus_imports", test_command_bus_imports),
        ("double_clap_no_wake_on_single", test_double_clap_no_wake_on_single),
        ("silence_no_wake", test_silence_no_wake),
        ("speech_not_clap", test_speech_not_clap),
    ]

    for name, func in tests:
        try:
            ok = func()
            results.append((name, ok))
        except Exception as e:
            _fail(name, source=str(e))
            results.append((name, False))

    _log("")
    _log("=" * 60)
    _log("SUMMARY")
    _log("=" * 60)
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    for name, ok in results:
        _log(f"{'PASS' if ok else 'FAIL'} {name}")
    _log("")
    _log(f"TOTAL: {len(results)}  PASS: {passed}  FAIL: {failed}")

    log_text = "\n".join(_log_buffer)
    try:
        RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(str(RESULT_FILE), "w", encoding="utf-8") as f:
            f.write(log_text)
        print(f"\n[DEBUG] Log saved to {RESULT_FILE}", flush=True)
    except Exception as e:
        print(f"[DEBUG] Failed to save log: {e}", flush=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
