import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_gemini_context_contains_need_profile():
    from engine.cognitive_context import set_last_strategy
    from engine.gemini_brain import _build_cognitive_context

    set_last_strategy({
        "chosen_route": "brain",
        "chosen_intent": "need_profile_task",
        "confidence": 0.9,
        "detected_need": "seo",
        "training_level": "medium",
        "need_profile_used": True,
        "style": "technical",
        "profile_rules_used": ["include technical fixes"],
        "active_need_profile": {
            "need_name": "seo",
            "level": "medium",
            "style": "technical",
            "output_preference": "workspace",
            "rules": ["include technical fixes"],
            "examples": [{"type": "example_rule", "text": "Ideal: concise priorities"}],
        },
    })
    context, _turns, _count, _model = _build_cognitive_context("SEO audit")
    assert "Training profile context" in context
    assert "current_need=seo" in context
    assert "include technical fixes" in context
