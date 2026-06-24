from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.tool_registry import list_tools


def main() -> int:
    for tool in list_tools():
        print(f"[TOOL] {tool['name']} safety={tool['safety']} required={','.join(tool['required_slots'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
