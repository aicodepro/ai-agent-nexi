import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class StopNow:
    def is_set(self):
        return True


def test_runpy_passes_queue_to_audio_process(monkeypatch):
    import run
    import engine.audio_wake_pipeline as awp

    q = object()
    seen = {}
    monkeypatch.setenv("VOICE_WAKE_BACKEND", "openwakeword")
    monkeypatch.setattr(awp, "start_audio_wake_pipeline", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr(awp, "is_pipeline_running", lambda: True)

    run.listenHotword(command_queue=q, stop_event=StopNow())

    assert seen["command_queue"] is q


def test_runpy_passes_queue_to_ui_process(monkeypatch):
    import run
    import main

    q = object()
    stop = object()
    calls = []
    monkeypatch.setattr(main, "main", lambda **kwargs: calls.append(kwargs))

    run.startNexi(command_queue=q, stop_event=stop)

    assert calls == [{"command_queue": q, "stop_event": stop}]


def test_openwakeword_backend_does_not_use_legacy_fallback_when_disabled(monkeypatch):
    import run
    import engine.audio_wake_pipeline as awp
    import engine.features as features

    monkeypatch.setenv("VOICE_WAKE_BACKEND", "openwakeword")
    monkeypatch.setenv("DISABLE_LEGACY_HOTWORD_FALLBACK", "true")
    monkeypatch.setattr(awp, "start_audio_wake_pipeline", lambda **kwargs: None)
    monkeypatch.setattr(awp, "is_pipeline_running", lambda: False)
    monkeypatch.setattr(awp, "get_last_start_error", lambda: "scorer_missing")
    legacy_hotword = MagicMock()
    legacy_clap = MagicMock()
    monkeypatch.setattr(features, "hotword_no_key", legacy_hotword)
    monkeypatch.setattr(features, "start_clap_if_enabled", legacy_clap)

    run.listenHotword(command_queue=object(), stop_event=StopNow())

    legacy_hotword.assert_not_called()
    legacy_clap.assert_not_called()


def test_audio_pipeline_logs_fatal_when_scorer_missing_and_fallback_disabled(monkeypatch, capsys):
    import run
    import engine.audio_wake_pipeline as awp

    monkeypatch.setenv("VOICE_WAKE_BACKEND", "openwakeword")
    monkeypatch.setenv("DISABLE_LEGACY_HOTWORD_FALLBACK", "true")
    monkeypatch.setattr(awp, "start_audio_wake_pipeline", lambda **kwargs: None)
    monkeypatch.setattr(awp, "is_pipeline_running", lambda: False)
    monkeypatch.setattr(awp, "get_last_start_error", lambda: "scorer_missing")

    run.listenHotword(command_queue=object(), stop_event=StopNow())

    out = capsys.readouterr().out
    assert "[WAKEPROC] fatal pipeline failed reason=scorer_missing" in out
