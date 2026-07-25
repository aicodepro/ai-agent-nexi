import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_long_answer_uses_summary_tts():
    from engine.tts_response_manager import build_spoken_text
    full = "Essay on humans. " + ("Humans build culture, tools, and communities. " * 40)
    max_chars = 700
    spoken = build_spoken_text(full, max_chars=max_chars)
    assert "Essay on humans" in spoken
    assert "Humans build culture, tools, and communities" in spoken
    assert spoken.endswith("I've put the full answer on screen.")
    assert len(spoken) < max_chars
    assert full not in spoken
