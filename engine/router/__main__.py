"""Try the Master Router from the terminal.

    python -m engine.router "open chrome and mute"      # one-shot
    python -m engine.router                              # interactive REPL

Prints the band (act/confirm/ask/chat), the chosen route/intent, the similarity
and margin, and the top-3 candidates — so you can see *why* it decided.
"""
from __future__ import annotations

import sys

from engine.router import route


def _show(text: str) -> None:
    d = route(text)
    print(f"{text!r}")
    print(f"  band={d.band}  route={d.route}  intent={d.intent}  "
          f"sim={d.sim:.2f}  margin={d.margin:.2f}  tier={d.tier}")
    if d.route == "react" and d.plan:
        print(f"  multi-step plan ({len(d.plan)} steps):")
        for i, step in enumerate(d.plan, 1):
            print(f"    {i}. {step.route}/{step.intent}  (band={step.band})")
        return
    if d.candidates:
        print("  top: " + ", ".join(f"{c.intent}({c.score:.2f})" for c in d.candidates[:3]))
    if d.route == "clarify":
        print("  ->", d.result["clarification_question"])


def main() -> None:
    if len(sys.argv) > 1:
        _show(" ".join(sys.argv[1:]))
        return
    print("Master Router REPL — type a command (blank line to quit)")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            break
        _show(text)


if __name__ == "__main__":
    main()
