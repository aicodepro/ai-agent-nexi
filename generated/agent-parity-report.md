# Agent Parity Report

<!-- GENERATED FROM config/agents/catalog.json - DO NOT EDIT BY HAND -->

| Surface | Count |
| --- | ---: |
| Runtime agents (catalog) | 15 |
| Studio agents (catalog) | 39 |
| Claude Code definitions generated | 54 |
| OpenCode definitions generated | 54 |
| Deterministic controllers | 9 |

Parity is structural: both runtimes are generated from the same catalog entries, so per-agent responsibility, permission intent and delegation boundaries cannot diverge by hand-editing. `--check` fails the build on drift.

## Controllers without a single authority

- `run-ledger` — **not implemented**

> Generated definitions are declarations, not activation. An agent is only live once it is wired to policy, routing and tests.
