import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_last_spoken_words_two_words():
    from engine.speech_progress import get_last_spoken_words
    assert get_last_spoken_words("Jarvis has put the answer on screen.") == "on screen"
    assert get_last_spoken_words("Ready") == "Ready"


def test_speech_capsule_never_uses_full_paragraph():
    from engine.speech_progress import get_last_spoken_words
    text = "This is a long paragraph that should never be shown fully in the speech capsule."
    result = get_last_spoken_words(text)
    assert result == "speech capsule"
    assert result != text
