import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "prompts"


def test_all_model_prompts_exist_and_use_nexi_identity():
    files = [
        "nexi_gemini_brain_system_prompt.txt",
        "nexi_groq_intent_system_prompt.txt",
        "nexi_safety_system_prompt.txt",
        "nexi_asr_prompt.txt",
        "nexi_tts_style_prompt.txt",
        "nexi_vision_system_prompt.txt",
        "nexi_mcp_tool_system_prompt.txt",
        "nexi_camera_control_prompt.txt",
        "nexi_clarification_system_prompt.txt",
        "compact_runtime_prompt.txt",
        "nexi_system_prompt.txt",
    ]
    skip_nexi_check = {"nexi_asr_prompt.txt"}
    for name in files:
        text = (PROMPTS / name).read_text(encoding="utf-8")
        assert "I am F.R.I.D.A.Y." not in text
        if name not in skip_nexi_check:
            assert "Nexi" in text


def test_gemini_identity_is_nexi():
    text = (PROMPTS / "nexi_gemini_brain_system_prompt.txt").read_text(encoding="utf-8")
    assert "Your name is Nexi." in text
    assert "You are not F.R.I.D.A.Y." in text


def test_no_prompt_renames_to_friday():
    for path in PROMPTS.glob("*.txt"):
        text = path.read_text(encoding="utf-8")
        assert "Your name is F.R.I.D.A.Y." not in text


def test_prompt_loader_fallback():
    from engine.prompt_loader import load_prompt_file
    assert load_prompt_file("missing_prompt.txt", "fallback") == "fallback"
