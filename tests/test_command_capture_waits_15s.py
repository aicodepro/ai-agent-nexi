from __future__ import annotations


def test_command_capture_waits_15s_for_speech():
    import engine.audio_wake_pipeline as awp

    # matches the module constant (and this test's own name): 15s
    assert awp.NO_SPEECH_TIMEOUT_SECONDS == 15.0

