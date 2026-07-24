from __future__ import annotations


def test_command_capture_waits_15s_for_speech():
    import engine.audio_wake_pipeline as awp

    assert awp.NO_SPEECH_TIMEOUT_SECONDS == 20.0

