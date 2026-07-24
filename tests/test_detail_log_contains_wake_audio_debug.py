from __future__ import annotations


def test_detail_log_contains_wake_audio_debug(monkeypatch, tmp_path):
    path = tmp_path / "nexi_interview_debug.log"
    monkeypatch.setenv("NEXI_DEBUG_LOG_FILE", str(path))

    from engine.debug_trace import detail

    detail("[AUDIO] frames=", frames=7, rms="0.003", peak="0.010")
    detail("[WAKE] score", score="0.251", threshold="0.25")

    text = path.read_text(encoding="utf-8")
    assert "[AUDIO] frames=" in text
    assert "[WAKE] score" in text
    assert "frames=7" in text

