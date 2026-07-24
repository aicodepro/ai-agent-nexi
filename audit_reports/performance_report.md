# Performance Report

Measured on 2026-07-23 with `.venv\Scripts\python.exe` on the local Windows development machine.

## Router V3

Benchmark: 50 deterministic `what time is it` routes.

- Median: 108.333 ms.
- p95: 161.140 ms.
- Maximum: 2005.668 ms.
- The maximum included cold initialization/background semantic-router warmup.

The warmed deterministic path is within an interactive voice-assistant budget. Cold startup should be hidden behind application warmup before first use; the observed 2-second maximum is not acceptable as steady-state latency.

## Live Search

Real no-key smoke query: `Python 3.12 release date`.

- Provider: DuckDuckGo.
- Live: true.
- Citations: 2.
- Provider errors: none.
- Stale fallback: false.

Provider timeouts are capped by `NEXI_LIVE_SEARCH_TIMEOUT_SECONDS`, default six seconds. Keyed Brave/Tavily performance was not measured because no credentials were supplied.

## Automated Test Durations

- Consolidated changed-surface regression gate: 429 tests in 170.35 seconds.
- Lifecycle focused gate: 61 tests in 66.47 seconds.
- Broader runtime/wake regression: 78 tests in 18.34 seconds.
- Router/command-bus integration: 77 tests in 20.93 seconds.
- Live intelligence/tool integration: 45 tests in 3.90 seconds.
- Spotify integration/router contracts: 46 tests in 13.86 seconds.
- Accessibility/transcript/browser/computer contracts: 44 tests in 17.91 seconds.
- Safety/approval/security contracts: 55 tests in 15.77 seconds.

The focused groups overlap. The consolidated 429-test gate is the unique selected-surface result.

## Unmeasured

- Wake-to-listen latency on physical microphone input.
- ASR provider latency and error rate.
- TTS first-audio latency and interrupt latency on real speakers.
- Brave/Tavily p50/p95 latency.
- Spotify search-to-audible-playback latency.
- UIA traversal latency across target desktop applications.
