import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_tts_long_answer_speaks_summary_only():
    from engine.tts_response_manager import build_spoken_text
    full = "Chocolate cake recipe. " + ("Mix ingredients and bake until done. " * 40)
    spoken = build_spoken_text(full, max_chars=120)
    assert len(spoken) < len(full)
    assert spoken.startswith("Here's the short version.")
    assert "full recipe on screen" in spoken


def test_tts_chunks_check_interrupt():
    from engine.tts_response_manager import split_tts_chunks
    text = ("One " * 90).strip() + ". " + ("Two " * 90).strip() + "."
    chunks = split_tts_chunks(text, max_chars=160)
    assert len(chunks) > 1
    assert all(len(chunk) <= 160 for chunk in chunks)
