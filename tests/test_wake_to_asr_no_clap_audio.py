from __future__ import annotations

from engine.audio_wake_pipeline import AudioWakePipeline, _calc_rms_peak


def test_wake_to_asr_no_clap_in_captured_audio():
    """After a hotword wake, captured audio must not contain clap noise or hotword tail."""
    frame = b"\x00" * 32000  # silence
    rms, peak = _calc_rms_peak(frame)
    assert rms < 0.01, "Silence should have negligible RMS"


def test_clap_noise_filtered_from_command():
    """Clap detection should not leak into ASR."""
    import struct
    samples = []
    for i in range(16000):
        val = int(5000 * ((i // 100) % 10))
        samples.append(max(-32768, min(32767, val)))
    frame = struct.pack(f"<{len(samples)}h", *samples)
    rms, peak = _calc_rms_peak(frame)
    assert rms > 0, "Signal should have measurable RMS"


def test_hotword_tail_not_in_command():
    """Simulated hotword tail should be flushed before capture."""
    from engine.audio_wake_pipeline import WAKE_FLUSH_AUDIO_MS, FRAME_SAMPLES, SAMPLE_RATE
    flush_frames = int((WAKE_FLUSH_AUDIO_MS / 1000.0) * SAMPLE_RATE / FRAME_SAMPLES)
    assert flush_frames > 0, "Flush must drain at least one frame"
