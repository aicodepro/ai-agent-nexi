from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hotword_manager_has_no_cloud_provider_imports():
    text = (ROOT / "engine" / "hotword_engine_manager.py").read_text(encoding="utf-8").lower()
    assert "groq" not in text
    assert "gemini" not in text
    assert "google_api_key" not in text


def test_audio_wake_process_frame_has_no_cloud_provider_calls():
    text = (ROOT / "engine" / "audio_wake_pipeline.py").read_text(encoding="utf-8").lower()
    section = text.split("def process_frame", 1)[1].split("def _post_status", 1)[0]
    assert "groq" not in section
    assert "gemini" not in section


def test_groq_asr_only_after_wake_capture():
    text = (ROOT / "engine" / "audio_wake_pipeline.py").read_text(encoding="utf-8")
    assert "def emit_command" in text
    assert "_default_asr" in text
    assert text.index("def emit_command") > text.index("def process_frame")
