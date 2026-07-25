import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_unverified_success_does_not_fake_completion():
    from engine.tool_result_verifier import verify_tool_result

    result = verify_tool_result(
        "open_app",
        {"success": True, "verified": False, "message": "Done. Opened Chrome."},
    )

    assert result["raw_success"] is True
    assert result["verified"] is False
    assert result["success"] is False
    assert result["ok"] is False
    assert "couldn't verify" in result["message"]


def test_open_app_verified_only_when_process_running(monkeypatch):
    import engine.tool_result_verifier as v

    monkeypatch.setattr(v, "_app_process_running", lambda app: True)
    ok = v.verify_tool_result("open_app", {"success": True, "app": "chrome", "message": "Opening chrome."})
    assert ok["verified"] is True
    assert ok["verification_reason"] == "process_running"

    monkeypatch.setattr(v, "_app_process_running", lambda app: False)
    bad = v.verify_tool_result("open_app", {"success": True, "app": "chrome", "message": "Opening chrome."})
    assert bad["verified"] is False
    assert bad["verification_reason"] == "process_not_found"
    assert "couldn't" in bad["message"].lower()


def test_open_app_without_app_name_stays_unverified():
    # No structured app name to check -> must not fake completion (honest downgrade).
    from engine.tool_result_verifier import verify_tool_result

    result = verify_tool_result("open_app", {"success": True, "verified": True, "message": "Done."})
    assert result["verified"] is False
    assert result["verification_reason"] == "unverified_success"


def test_open_app_verifier_failure_is_not_reported_as_process_missing(monkeypatch):
    import engine.tool_result_verifier as v

    monkeypatch.setattr(v, "_app_process_running", lambda _app: None)
    result = v.verify_tool_result("open_app", {"success": True, "app": "chrome", "message": "Opening chrome."})

    assert result["verified"] is False
    assert result["verification_reason"] == "verification_unavailable"


def test_file_tool_success_requires_existing_path(tmp_path):
    from engine.tool_result_verifier import verify_tool_result

    target = tmp_path / "created.txt"
    missing = verify_tool_result("create_file", {"success": True, "path": str(target), "message": "File created."})
    assert missing["success"] is False
    assert missing["verification_reason"] == "path_missing"

    target.write_text("created", encoding="utf-8")
    verified = verify_tool_result("create_file", {"success": True, "path": str(target), "message": "File created."})
    assert verified["success"] is True
    assert verified["verified"] is True
    assert verified["verification_reason"] == "path_exists"


def test_file_tool_cannot_self_verify_without_path():
    from engine.tool_result_verifier import verify_tool_result

    result = verify_tool_result(
        "create_file",
        {"success": True, "verified": True, "message": "File created."},
    )

    assert result["success"] is False
    assert result["verified"] is False
    assert result["verification_reason"] == "verification_data_missing"


def test_file_verifier_failure_is_reported_as_unavailable(monkeypatch):
    import engine.tool_result_verifier as v

    def fail(_path):
        raise OSError("disk unavailable")

    monkeypatch.setattr(v.Path, "exists", fail)
    result = v.verify_tool_result("create_file", {"success": True, "path": "created.txt"})

    assert result["verified"] is False
    assert result["verification_reason"] == "verification_unavailable"


def test_success_without_verification_strategy_is_reported_honestly():
    from engine.tool_result_verifier import verify_tool_result

    result = verify_tool_result("custom_action", {"success": True, "message": "Done."})

    assert result["success"] is False
    assert result["verified"] is False
    assert result["verification_reason"] == "verification_unavailable"
    assert "couldn't verify" in result["message"].lower()


def test_handler_verified_success_without_external_strategy_is_preserved():
    from engine.tool_result_verifier import verify_tool_result

    result = verify_tool_result("custom_action", {"success": True, "verified": True, "message": "Done."})

    assert result["success"] is True
    assert result["verified"] is True
    assert result["verification_reason"] == "explicit_verified"
