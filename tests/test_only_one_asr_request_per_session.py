from __future__ import annotations


def test_only_one_asr_request_per_session():
    from engine.audio_wake_pipeline import AudioWakePipeline

    calls = []

    def asr(audio, sample_rate):
        calls.append((audio, sample_rate))
        return "open chrome"

    pipeline = AudioWakePipeline(on_command_text=lambda text: None, asr=asr)
    assert pipeline.emit_command(b"\x01\x00" * 24000, source="hotword") == "open chrome"
    assert len(calls) == 1

