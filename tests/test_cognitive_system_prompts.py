import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def test_prompt_says_not_conscious():
    text = (PROMPTS / "nexi_gemini_brain_system_prompt.txt").read_text(encoding="utf-8")
    assert "not truly conscious or sentient" in text
    assert "Never say \"I am conscious.\"" in text


def test_prompt_identity_is_nexi():
    text = (PROMPTS / "nexi_system_prompt.txt").read_text(encoding="utf-8")
    assert "Your name is Nexi." in text
    assert "You are not F.R.I.D.A.Y." in text
