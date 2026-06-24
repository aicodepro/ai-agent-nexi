import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestToolCategoryView:
    def test_get_tool_categories(self):
        from engine.tool_category_view import get_tool_categories
        cats = get_tool_categories()
        assert isinstance(cats, dict)
        assert len(cats) > 0

    def test_categories_have_required_keys(self):
        from engine.tool_category_view import get_tool_categories
        cats = get_tool_categories()
        required = {"label", "description", "tools", "risk", "suggestion"}
        for key, cat in cats.items():
            for r in required:
                assert r in cat, f"Category {key} missing {r}"

    def test_risk_levels_valid(self):
        from engine.tool_category_view import get_tool_categories
        cats = get_tool_categories()
        for cat in cats.values():
            assert cat["risk"] in {"safe", "confirm", "dangerous"}, f"Invalid risk level: {cat['risk']}"

    def test_get_command_suggestions(self):
        from engine.tool_category_view import get_command_suggestions
        suggestions = get_command_suggestions()
        assert isinstance(suggestions, list)
        assert len(suggestions) > 0
        for s in suggestions:
            assert "label" in s
            assert "text" in s

    def test_suggestions_have_safe_text(self):
        from engine.tool_category_view import get_command_suggestions
        suggestions = get_command_suggestions()
        dangerous = {"exec", "eval", "rm -rf", "delete system"}
        for s in suggestions:
            for d in dangerous:
                assert d not in s["text"].lower(), f"Suggestion contains dangerous command: {s['text']}"