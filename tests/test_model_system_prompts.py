import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"


def test_all_model_prompts_exist_and_use_jarvis_identity():
    files = [
        "jarvis_gemini_brain_system_prompt.txt",
        "jarvis_groq_intent_system_prompt.txt",
        "jarvis_safety_system_prompt.txt",
        "jarvis_asr_prompt.txt",
        "jarvis_tts_style_prompt.txt",
        "jarvis_vision_system_prompt.txt",
        "jarvis_mcp_tool_system_prompt.txt",
        "jarvis_camera_control_prompt.txt",
        "jarvis_clarification_system_prompt.txt",
        "compact_runtime_prompt.txt",
        "jarvis_system_prompt.txt",
    ]
    skip_jarvis_check = {"jarvis_asr_prompt.txt"}
    for name in files:
        text = (PROMPTS / name).read_text(encoding="utf-8")
        assert "I am F.R.I.D.A.Y." not in text
        if name not in skip_jarvis_check:
            assert "Jarvis" in text


def test_gemini_identity_is_jarvis():
    text = (PROMPTS / "jarvis_gemini_brain_system_prompt.txt").read_text(encoding="utf-8")
    assert "Your name is Jarvis." in text
    assert "You are not F.R.I.D.A.Y." in text


def test_no_prompt_renames_to_friday():
    for path in PROMPTS.glob("*.txt"):
        text = path.read_text(encoding="utf-8")
        assert "Your name is F.R.I.D.A.Y." not in text


def test_prompt_loader_fallback():
    from engine.prompt_loader import load_prompt_file
    assert load_prompt_file("missing_prompt.txt", "fallback") == "fallback"
