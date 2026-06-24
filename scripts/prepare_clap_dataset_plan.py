from __future__ import annotations

import argparse
import json


SOURCES = [
    {
        "name": "Hugging Face ESC-50",
        "purpose": "clapping positives plus environmental negatives",
        "download": "manual approval required",
    },
    {
        "name": "Kaggle ESC-50",
        "purpose": "ESC-50 mirror candidate",
        "download": "manual approval required",
    },
    {
        "name": "Kaggle Freesound Audio Tagging",
        "purpose": "clap/applause positives and broad negatives",
        "download": "manual approval required",
    },
    {
        "name": "Kaggle audio_clap_feat",
        "purpose": "inspect clap feature provenance before any use",
        "download": "manual approval required",
    },
]

LOCAL_RECORDING_TARGETS = {
    "single_clap_positive": 100,
    "double_clap_positive": 150,
    "near_miss_negative": 150,
    "speech_negative": 150,
    "ambient_negative": 200,
}

METRICS = [
    "precision",
    "recall",
    "false_positives_per_minute",
    "wake_latency_ms",
    "double_clap_gap_acceptance_rate",
    "cooldown_repeat_wake_suppression_rate",
    "long_audio_rejection_rate",
]


def build_plan() -> dict:
    return {
        "verdict": "plan_only_no_downloads",
        "sources": SOURCES,
        "local_recording_targets": LOCAL_RECORDING_TARGETS,
        "metrics": METRICS,
        "split_rule": "split by recording session, room, mic gain, and user",
        "safety": [
            "no automatic dataset downloads",
            "no training during judge-demo hardening",
            "no unknown pickle or model loading without approval",
        ],
    }


def format_markdown(plan: dict) -> str:
    lines = ["# Clap Dataset Plan", "", f"Verdict: {plan['verdict']}", "", "## Sources"]
    for source in plan["sources"]:
        lines.append(f"- {source['name']}: {source['purpose']} ({source['download']})")
    lines.extend(["", "## Local Recording Targets"])
    for name, count in plan["local_recording_targets"].items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## Metrics"])
    for metric in plan["metrics"]:
        lines.append(f"- {metric}")
    lines.extend(["", f"Split rule: {plan['split_rule']}"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Print the Nexi clap dataset research plan without downloading data.")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()
    plan = build_plan()
    if args.format == "json":
        print(json.dumps(plan, indent=2))
    else:
        print(format_markdown(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
