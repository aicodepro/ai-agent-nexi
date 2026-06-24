from __future__ import annotations

from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def load_prompt_file(path: str, fallback: str = "") -> str:
    try:
        prompt_path = Path(path)
        if not prompt_path.is_absolute():
            prompt_path = PROMPTS_DIR / prompt_path
        text = prompt_path.read_text(encoding="utf-8").strip()
        return text or fallback
    except Exception:
        return fallback
