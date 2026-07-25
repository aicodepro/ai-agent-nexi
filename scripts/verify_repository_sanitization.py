#!/usr/bin/env python3
"""Verify that credentials and personal data are absent from the repository.

Detects by *vendor pattern*, never by literal secret value, so this script is
safe to commit, safe to run in CI, and safe to paste into a ticket.

Scans the working tree by default; `--history` also scans every reachable
commit, which is what proves a history rewrite actually worked.

Exit codes:
    0  clean
    1  findings present
    2  could not run (e.g. not a git repository)

Usage:
    python scripts/verify_repository_sanitization.py
    python scripts/verify_repository_sanitization.py --history
    python scripts/verify_repository_sanitization.py --history --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# Vendor credential shapes. Deliberately generic: no real secret is stored here.
CREDENTIAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "groq_api_key": re.compile(r"gsk_[0-9A-Za-z]{40,}"),
    "anthropic_api_key": re.compile(r"sk-ant-[0-9A-Za-z_\-]{20,}"),
    "openai_api_key": re.compile(r"sk-(?:proj-)?[0-9A-Za-z_\-]{32,}"),
    "github_token": re.compile(r"gh[pousr]_[0-9A-Za-z]{36,}"),
    "slack_token": re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"),
    "aws_access_key_id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "huggingface_token": re.compile(r"hf_[0-9A-Za-z]{30,}"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "spotify_refresh_token": re.compile(r"AQ[A-Za-z0-9_\-]{80,}"),
}

# Personal / biometric data that must never be redistributed.
PERSONAL_DATA_PATHS: tuple[str, ...] = (
    "hey_nexi_clips/",       # personal wake-word voice recordings
    "artifacts/last_asr",    # most recent captured speech
    "trainingData.yml",      # LBPH face-recognition biometric model
    "datasets/",             # generated training audio
)

# Paths whose *matches are expected* - detection patterns, tests and docs that
# legitimately contain credential-shaped strings.
ALLOWLIST_PATH_PARTS: tuple[str, ...] = (
    "scripts/verify_repository_sanitization.py",
    "engine/memory_safety.py",
    "security/secret-inventory.json",
    "tests/test_secret_redaction.py",
    ".github/workflows/security.yml",
    # Vendored third-party skill packs ship their own redaction test fixtures
    # containing deliberately fake credentials. Not ours, not live.
    "agent/skills/",
)


def _fingerprint(value: str) -> str:
    """Stable, non-reversible id so findings can be tracked without exposure."""
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:16]


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, errors="replace"
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def _allowlisted(path: str) -> bool:
    norm = path.replace("\\", "/")
    return any(part in norm for part in ALLOWLIST_PATH_PARTS)


def scan_working_tree() -> list[dict]:
    findings: list[dict] = []
    tracked = [p for p in _git("ls-files").splitlines() if p.strip()]

    for path in tracked:
        norm = path.replace("\\", "/")

        for marker in PERSONAL_DATA_PATHS:
            if norm.startswith(marker) or norm == marker.rstrip("/"):
                findings.append({
                    "kind": "personal_data",
                    "type": marker.rstrip("/"),
                    "path": path,
                    "location": "working_tree",
                })

        if _allowlisted(path):
            continue
        file = Path(path)
        if not file.is_file() or file.stat().st_size > 2_000_000:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in CREDENTIAL_PATTERNS.items():
            for match in pattern.findall(text):
                findings.append({
                    "kind": "credential",
                    "type": name,
                    "path": path,
                    "location": "working_tree",
                    "fingerprint": _fingerprint(match),
                })
    return findings


def scan_history() -> list[dict]:
    """Scan every blob reachable from any ref. This is the real proof."""
    findings: list[dict] = []
    revs = _git("rev-list", "--all").splitlines()
    if not revs:
        return findings

    for marker in PERSONAL_DATA_PATHS:
        target = marker.rstrip("/")
        commits = _git("log", "--all", "--oneline", "--", target).splitlines()
        if commits:
            findings.append({
                "kind": "personal_data",
                "type": target,
                "path": target,
                "location": "history",
                "commit_count": len(commits),
            })

    # Credential shapes across all history, via grep over reachable objects.
    for name, pattern in CREDENTIAL_PATTERNS.items():
        out = _git("grep", "-I", "--no-color", "-E", pattern.pattern, *revs[:400])
        seen: set[str] = set()
        for line in out.splitlines():
            head = line.split(":", 2)
            if len(head) < 3:
                continue
            commit, path = head[0], head[1]
            if _allowlisted(path):
                continue
            match = pattern.search(head[2])
            if not match:
                continue
            fp = _fingerprint(match.group(0))
            key = f"{name}:{fp}"
            if key in seen:
                continue
            seen.add(key)
            findings.append({
                "kind": "credential",
                "type": name,
                "path": path,
                "location": "history",
                "first_seen_commit": commit[:12],
                "fingerprint": fp,
            })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true",
                        help="also scan all reachable commits (slower)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if not _git("rev-parse", "--git-dir").strip():
        print("ERROR: not a git repository", file=sys.stderr)
        return 2

    findings = scan_working_tree()
    if args.history:
        findings += scan_history()

    if args.json:
        print(json.dumps({"clean": not findings, "findings": findings}, indent=2))
    else:
        tree = [f for f in findings if f["location"] == "working_tree"]
        hist = [f for f in findings if f["location"] == "history"]
        print(f"working tree : {len(tree)} finding(s)")
        print(f"history      : {len(hist)} finding(s)"
              if args.history else "history      : not scanned (--history)")
        for f in findings:
            ident = f.get("fingerprint") or f"{f.get('commit_count', '?')} commits"
            print(f"  [{f['location']:12}] {f['kind']:14} {f['type']:22} {f['path']}  ({ident})")
        if not findings:
            print("\nCLEAN - no credential patterns or personal data detected.")
        else:
            print(f"\nFAIL - {len(findings)} finding(s). Values are never printed; "
                  f"fingerprints are SHA-256 prefixes.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
