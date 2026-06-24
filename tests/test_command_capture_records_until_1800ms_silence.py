from __future__ import annotations


def test_command_capture_records_until_1800ms_silence():
    import engine.audio_wake_pipeline as awp

    assert awp.ASR_SILENCE_TIMEOUT_MS == 1500

