from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ui_has_draggable_workspace():
    index = (ROOT / "www" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "www" / "style.css").read_text(encoding="utf-8")
    js = (ROOT / "www" / "controller.js").read_text(encoding="utf-8")
    assert "NexiOutputWorkspace" in index
    assert "nexi-output-workspace" in css
    assert "makeWorkspaceDraggable" in js


def test_ui_workspace_has_copy_save_buttons():
    index = (ROOT / "www" / "index.html").read_text(encoding="utf-8")
    assert "WorkspaceCopyBtn" in index
    assert "WorkspaceCreateFileBtn" in index
    assert "WorkspaceSaveMdBtn" in index
