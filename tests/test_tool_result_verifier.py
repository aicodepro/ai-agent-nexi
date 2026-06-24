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
