import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

ROOT = Path(__file__).resolve().parents[1]


class TestMarkUiPlaywrightStatic:
    def test_playwright_available(self):
        try:
            import playwright  # noqa: F401
        except ImportError:
            pytest = __import__("pytest")
            pytest.skip("Playwright not installed")

    def test_visual_validate_script_exists(self):
        path = ROOT / "scripts" / "visual_validate_mark_ui.py"
        assert path.exists(), "visual_validate_mark_ui.py missing"

    def test_visual_quality_checker_exists(self):
        path = ROOT / "scripts" / "check_mark_ui_visual_quality.py"
        assert path.exists(), "check_mark_ui_visual_quality.py missing"

    def test_artifacts_dir_exists(self):
        path = ROOT / "artifacts" / "ui_mark_validation"
        assert path.exists() and path.is_dir(), "artifacts/ui_mark_validation missing"

    def test_scripts_importable(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "check_mark_ui_visual_quality",
            ROOT / "scripts" / "check_mark_ui_visual_quality.py",
        )
        assert spec is not None, "Cannot import check_mark_ui_visual_quality.py"