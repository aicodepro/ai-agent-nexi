from __future__ import annotations


def test_detail_log_contains_frame_debug(monkeypatch, tmp_path):
    path = tmp_path / "jarvis_interview_debug.log"
    monkeypatch.setenv("JARVIS_DEBUG_LOG_FILE", str(path))

    from engine.debug_trace import detail

    detail("[AUDIO] frames=", frames=12, rms="0.004")

    text = path.read_text(encoding="utf-8")
    assert "[AUDIO] frames=" in text
    assert "frames=12" in text

