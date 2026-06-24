import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_requested_skill_files_exist_and_are_compact():
    root = Path(__file__).resolve().parents[1]
    names = [
        "karpathy-debugging",
        "nexi-architecture",
        "nexi-model-router",
        "nexi-safety-gate",
        "nexi-workflow-dialogue",
        "nexi-ui-debug",
    ]
    for name in names:
        path = root / ".opencode" / "skills" / name / "SKILL.md"
        assert path.exists(), path
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 120
