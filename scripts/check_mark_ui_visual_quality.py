"""Check Mark UI visual quality from screenshots and DOM."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "ui_mark_validation"
WWW_MARK = ROOT / "www_mark"

EXPECTED_SCREENSHOTS = [
    "mark_ui_1366x768.png",
    "mark_ui_1920x1080.png",
    "mark_ui_idle.png",
    "mark_ui_listening.png",
    "mark_ui_thinking.png",
    "mark_ui_speaking.png",
]

REQUIRED_HTML_IDS = [
    "top-header",
    "left-panel",
    "center-stage",
    "hud-canvas",
    "right-panel",
    "command-bar",
    "command-input",
    "mic-button",
    "power-button",
    "settings-button",
    "settings-overlay",
    "debug-panel",
    "file-drop-zone",
    "state-badge",
    "activity-log",
    "waveform",
    "suggestion-list",
]


def main():
    issues = []

    index_html = WWW_MARK / "index.html"
    if not index_html.exists():
        issues.append("FATAL: www_mark/index.html missing")
        return report(issues)

    text = index_html.read_text(encoding="utf-8", errors="replace")

    # Check required IDs
    for id_str in REQUIRED_HTML_IDS:
        if f'id="{id_str}"' not in text and f"id='{id_str}'" not in text:
            issues.append(f"MISSING ID: {id_str}")

    # Check CSS file
    css_path = WWW_MARK / "style.css"
    if not css_path.exists():
        issues.append("FATAL: style.css missing")
    else:
        css_text = css_path.read_text(encoding="utf-8", errors="replace")
        if "grid-template-columns" not in css_text:
            issues.append("CSS: grid-template-columns missing from style.css")
        if "grid-template-rows" not in css_text:
            issues.append("CSS: grid-template-rows missing from style.css")

    # Check JS files
    for js_file in ["main.js", "controller.js", "hud_orb.js"]:
        path = WWW_MARK / js_file
        if not path.exists():
            issues.append(f"FATAL: {js_file} missing")

    # Check logo
    logo = WWW_MARK / "assets" / "nexi-logo.svg"
    if not logo.exists():
        issues.append("MISSING: nexi-logo.svg")
    else:
        size = logo.stat().st_size
        if size < 100:
            issues.append(f"SUSPECT: nexi-logo.svg too small ({size} bytes)")

    # Check screenshots
    for s in EXPECTED_SCREENSHOTS:
        path = ARTIFACTS / s
        if not path.exists():
            issues.append(f"MISSING SCREENSHOT: {s}")
        else:
            size = path.stat().st_size
            if size < 1000:
                issues.append(f"SUSPECT SCREENSHOT: {s} too small ({size} bytes)")

    # Check HUD canvas centered in center-stage
    if "center-stage" in text and "hud-canvas" in text:
        print("CHECK: center-stage contains hud-canvas: OK")
    else:
        issues.append("LAYOUT: center-stage missing hud-canvas child")

    # Check no horizontal overflow
    css_text = (WWW_MARK / "style.css").read_text(encoding="utf-8", errors="replace")
    if "overflow: hidden" in css_text or "overflow-x: hidden" in css_text:
        print("CHECK: overflow hidden present: OK")
    else:
        issues.append("CSS: no overflow:hidden on body/html")

    return report(issues)


def report(issues):
    print("=" * 50)
    print("MARK UI VISUAL QUALITY CHECK")
    print("=" * 50)
    if not issues:
        print("PASS — No issues found")
        return True
    print(f"FAIL — {len(issues)} issue(s):")
    for i in issues:
        print(f"  {i}")
    return False


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)