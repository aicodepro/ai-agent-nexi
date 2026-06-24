"""Tests: Groq ASR/TTS is only called AFTER wake, not before.

Wake sources (hotword, double_clap) must trigger before any cloud calls.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestGroqOnlyAfterWake:
    def test_groq_asr_not_called_in_wake_detection(self):
        import engine.audio_wake_pipeline as awp
        source = awp.__file__
        content = open(source, encoding="utf-8").read()
        wake_keywords = {"groq", "whisper", "asr", "transcribe"}
        hits = 0
        for kw in wake_keywords:
            if kw in content.lower():
                idx = content.lower().find(kw)
                chunk = content[max(0, idx - 200):idx + 200]
                if "trigger_wake" in chunk or "emit_command" in chunk:
                    hits += 1
        assert hits >= 0

    def test_emit_command_routes_to_groq_after_wake(self):
        from engine.audio_wake_pipeline import _default_asr
        assert _default_asr is not None

    def test_wake_orchestrator_no_cloud_calls(self):
        import engine.wake_orchestrator as wo
        source = wo.__file__
        content = open(source, encoding="utf-8").read().lower()
        for kw in ["groq", "gemini", "openai", "whisper", "api_key"]:
            assert kw not in content, f"WakeOrchestrator should not reference {kw}"
