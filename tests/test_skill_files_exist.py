import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# `.opencode/` is untracked local tooling config — it is not in git, so a fresh clone (or
# CI, or a second machine) has no skills directory and this test would fail for a reason
# that has nothing to do with the product. Skip when the tooling isn't installed; still
# assert the contents when it is.
_SKILLS_DIR = Path(__file__).resolve().parents[1] / ".opencode" / "skills"

pytestmark = pytest.mark.skipif(
    not _SKILLS_DIR.is_dir(), reason=".opencode/skills not present (untracked local tooling)"
)


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
