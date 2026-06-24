import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestFileDropWorkflowSafe:
    def test_empty_file_list_rejected(self):
        from engine.ui_adapter import submit_file_drop
        result = submit_file_drop([])
        assert result["ok"] is False

    def test_null_file_list_rejected(self):
        from engine.ui_adapter import submit_file_drop
        result = submit_file_drop(None)
        assert result["ok"] is False

    def test_file_drop_returns_prompt(self):
        from engine.ui_adapter import submit_file_drop
        result = submit_file_drop(["C:/fake/file.txt"])
        assert result["ok"] is True
        assert "prompt" in result
        assert "files" in result

    def test_file_drop_max_files(self):
        from engine.ui_adapter import submit_file_drop
        many = [f"C:/file{i}.txt" for i in range(20)]
        result = submit_file_drop(many)
        assert len(result["files"]) <= 5

    def test_file_drop_does_not_read_content(self):
        from engine.ui_adapter import submit_file_drop
        result = submit_file_drop(["C:/test.txt"])
        for f in result["files"]:
            assert "content" not in f, "File drop must not read file contents automatically"
            assert "data" not in f, "File drop must not read file contents automatically"