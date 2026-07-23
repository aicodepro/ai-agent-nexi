"""Calibration scorer — turns "feels better" into a number.

Runs the Master Router over a labeled set of real utterances and reports:
    WHEN accuracy   — did it correctly treat commands as commands and talk as talk
    WHERE accuracy  — of the commands, did it pick the right tool/intent
    over-act        — chat wrongly executed as a command  (the scary error)
    over-ask        — a clear command bounced to a clarifying question

Usage:
    python -m engine.router.calibration.score           # summary
    python -m engine.router.calibration.score -v         # per-utterance detail
    python -m engine.router.calibration.score path.jsonl # custom set

Every migration phase must not regress these numbers.
"""
from __future__ import annotations

import json
import os
import sys

from engine.router import route

_HERE = os.path.dirname(__file__)
_DEFAULT_SET = os.path.join(_HERE, "utterances.jsonl")

_ACTION_ROUTES = {"tool", "output"}


def _load(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def score(path: str = _DEFAULT_SET, verbose: bool = False) -> dict:
    rows = _load(path)
    counts = {"action": 0, "chat": 0, "ambiguous": 0}
    when_ok = 0
    where_ok = 0            # correct intent among action items
    where_total = 0
    over_act = 0            # chat -> command
    over_ask = 0           # action -> clarify

    for row in rows:
        kind, expect = row["kind"], row.get("intent")
        d = route(row["text"])
        acted = d.route in _ACTION_ROUTES
        counts[kind] = counts.get(kind, 0) + 1

        if kind == "action":
            where_total += 1
            when_correct = d.route != "brain"      # any command-side outcome (act/confirm/ask)
            when_ok += int(when_correct)
            if d.route == "clarify":
                over_ask += 1
            if acted and d.intent == expect:
                where_ok += 1
            verdict = "OK" if (acted and d.intent == expect) else ("ASK" if d.route == "clarify" else "MISS")
        elif kind == "chat":
            when_correct = d.route == "brain"
            when_ok += int(when_correct)
            if acted:
                over_act += 1
            verdict = "OK" if when_correct else ("OVER-ACT" if acted else "ASK")
        else:  # ambiguous
            when_correct = d.route == "clarify"
            when_ok += int(when_correct)
            verdict = "OK" if when_correct else "LEAK"

        if verbose:
            print(f"  [{verdict:8}] {row['text'][:40]:40} -> {d.band:7} {d.route}/{d.intent}"
                  f"  sim={d.sim:.2f} margin={d.margin:.2f}")

    total = len(rows)
    summary = {
        "total": total,
        "when_accuracy": round(when_ok / total, 3) if total else 0.0,
        "where_accuracy": round(where_ok / where_total, 3) if where_total else 0.0,
        "over_act": over_act,
        "over_ask": over_ask,
        "counts": counts,
    }
    print("\n=== Master Router calibration ===")
    print(f"utterances      : {total}  {counts}")
    print(f"WHEN accuracy   : {summary['when_accuracy']:.1%}  (command-vs-talk correct)")
    print(f"WHERE accuracy  : {summary['where_accuracy']:.1%}  (right tool, of {where_total} commands)")
    print(f"over-act        : {over_act}  (chat wrongly executed — the scary one)")
    print(f"over-ask        : {over_ask}  (clear command bounced to a question)")
    return summary


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "-v"]
    verbose = "-v" in sys.argv[1:]
    score(args[0] if args else _DEFAULT_SET, verbose=verbose)
