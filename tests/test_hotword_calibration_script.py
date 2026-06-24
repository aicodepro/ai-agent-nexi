import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_hotword_calibration_declares_required_attempts_and_local_only():
    import scripts.debug_hotword_calibration as script

    assert script.PHRASE_ATTEMPTS == {"hey jarvis": 10, "jarvis": 10}
    assert script.SILENCE_SECONDS == 60
    assert "Groq" in script.LOCAL_ONLY_NOTICE
    assert "cloud" in script.LOCAL_ONLY_NOTICE.lower()


def test_hotword_calibration_recommendation_requires_meaningful_score():
    import scripts.debug_hotword_calibration as script

    rec = script.recommend_threshold([0.01, 0.02, 0.03])
    assert rec["recommended_threshold"] is None
    assert "model" in rec["reason"]
