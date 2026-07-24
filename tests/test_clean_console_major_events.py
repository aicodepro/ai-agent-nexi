from __future__ import annotations


def test_clean_console_prints_major_only(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("NEXI_CONSOLE_LOG_LEVEL", "clean")
    monkeypatch.setenv("NEXI_DEBUG_LOG_FILE", str(tmp_path / "debug.log"))

    from engine import debug_trace

    debug_trace.reset_for_tests()
    debug_trace.major("LISTENING")
    debug_trace.detail("[AUDIO] frames=1", rms="0.01")

    out = capsys.readouterr().out
    assert "LISTENING" in out
    assert "[AUDIO]" not in out

