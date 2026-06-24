from __future__ import annotations


def test_command_capture_tolerates_low_speech_ms_if_record_valid():
    from engine.audio_wake_pipeline import ASR_MIN_AUDIO_MS, AudioWakePipeline

    pipeline = AudioWakePipeline()
    assert pipeline._check_vad_gates({
        "speech_started": True,
        "duration_ms": ASR_MIN_AUDIO_MS,
        "speech_ms": 240,
        "max_rms": 0.02,
    })

