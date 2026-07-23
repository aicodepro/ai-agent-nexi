import os
import sys
import threading
import time

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


def test_latest_output_updates_are_serialized(monkeypatch):
    from engine import output_actions

    guard = threading.Lock()
    active = 0
    max_active = 0

    def slow_redact(text):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with guard:
            active -= 1
        return text

    monkeypatch.setattr(output_actions, "redact_sensitive", slow_redact)
    threads = [threading.Thread(target=output_actions.set_latest_output, args=(str(i),)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1
