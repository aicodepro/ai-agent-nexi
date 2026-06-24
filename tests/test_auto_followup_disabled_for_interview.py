from __future__ import annotations

from pathlib import Path


def test_auto_followup_disabled_for_interview():
    text = Path(".env.example").read_text(encoding="utf-8")
    assert "NEXI_AUTO_FOLLOWUP_AFTER_TTS=false" in text

