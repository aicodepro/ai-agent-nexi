import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_copy_latest_output(monkeypatch):
    from engine import output_actions
    output_actions.set_latest_output("hello", "Test", "text", "hello")
    monkeypatch.setitem(sys.modules, "pyperclip", type("P", (), {"copy": staticmethod(lambda text: None)}))
    assert output_actions.copy_latest_output()["ok"] is True


def test_create_file_requires_filename(tmp_path, monkeypatch):
    from engine import output_actions
    monkeypatch.setattr(output_actions, "OUTPUT_DIR", tmp_path)
    output_actions.set_latest_output("hello", "Test", "text", "hello")
    assert output_actions.create_output_file()["requires_filename"] is True


def test_save_file_sanitizes_filename(tmp_path, monkeypatch):
    from engine import output_actions
    monkeypatch.setattr(output_actions, "OUTPUT_DIR", tmp_path)
    output_actions.set_latest_output("hello", "Test", "text", "hello")
    result = output_actions.create_output_file("bad:name")
    assert result["ok"] is True
    assert "bad_name" in result["path"]


def test_no_overwrite_without_confirmation(tmp_path, monkeypatch):
    from engine import output_actions
    monkeypatch.setattr(output_actions, "OUTPUT_DIR", tmp_path)
    output_actions.set_latest_output("hello", "Test", "text", "hello")
    output_actions.create_output_file("same")
    assert output_actions.create_output_file("same")["requires_confirmation"] is True


def test_show_latest_output():
    from engine import output_actions
    output_actions.set_latest_output("hello", "Test", "text", "hello")
    assert output_actions.reopen_latest_output()["ok"] is True
