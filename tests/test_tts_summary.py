import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_long_answer_uses_summary_tts():
    from engine.tts_response_manager import build_spoken_text
    full = "Essay on humans. " + ("Humans build culture, tools, and communities. " * 40)
    spoken = build_spoken_text(full, max_chars=700)
    assert spoken == "Here's the short version. I've put the full answer on screen."
    assert len(spoken) < len(full)
