from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_prompt_says_adaptive_memory_not_consciousness():
    text = (ROOT / "prompts" / "jarvis_gemini_brain_system_prompt.txt").read_text(encoding="utf-8")
    assert "adaptive memory, not consciousness" in text


def test_prompt_mentions_last_10_turns():
    text = (ROOT / "prompts" / "jarvis_gemini_brain_system_prompt.txt").read_text(encoding="utf-8")
    assert "last 10 chat turns" in text


def test_prompt_identity_is_jarvis():
    text = (ROOT / "prompts" / "jarvis_gemini_brain_system_prompt.txt").read_text(encoding="utf-8")
    assert "Your name is Jarvis." in text
    assert "You are not F.R.I.D.A.Y." in text


def test_prompt_never_renames_jarvis():
    text = (ROOT / "prompts" / "jarvis_gemini_brain_system_prompt.txt").read_text(encoding="utf-8")
    assert "Your name is Jarvis." in text
    assert "Your name is F.R.I.D.A.Y." not in text


def test_prompt_contains_workspace_behavior():
    text = (ROOT / "prompts" / "jarvis_system_prompt.txt").read_text(encoding="utf-8")
    assert "Jarvis Output Workspace" in text
    assert "copy it" in text
