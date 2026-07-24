import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_intent_explainer_gives_safe_explanation():
    from engine.intent_explainer import explain_intent

    explanation = explain_intent(
        {
            "route": "tool",
            "intent": "web_search",
            "confidence": 0.97,
            "slots": {"query": "private search text"},
            "reason": "tool alias matched",
        },
        selected_tool="web_search",
        selected_rule="rule-id-that-should-not-be-spoken",
    )

    assert "tool/web_search" in explanation
    assert "Selected tool: web_search." in explanation
    assert "Selected rule: correction rule." in explanation
    assert "private search text" not in explanation
    assert "rule-id-that-should-not-be-spoken" not in explanation
