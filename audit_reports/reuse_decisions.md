# Mark-L Reuse Decisions

## Adopt As Product Patterns

- Multi-mode live search: search, news, research, price, compare.
- Provider fallback and parallel retrieval, but rank/corroborate results rather than accepting the first long response.
- Immediate acknowledgement before slow vision or research operations.
- Bounded user memory grouped by meaningful categories.
- Consumed session briefing entries that do not repeat forever.
- Local model health probes, model availability checks, and warmup.
- Offline faster-whisper settings that disable previous-text conditioning.

## Reimplement Clean-Room

- Search provider adapters and citation extraction.
- Temporal memory schema and briefing consumption.
- Provider health/warmup integration.
- Proactive notifications and monitoring.

No Mark-L source code should be copied into Nexi. The new implementation must use Nexi naming, interfaces, safety gates, tests, and typed receipts.

## Reject

- A monolithic `main.py` as combined router, session, tool, and response authority.
- Global monkey-patching of `subprocess.Popen`.
- Runtime package installation or upgrade from the TTS path.
- Plain JSON API-key storage.
- Generated passwords or identity data as a general desktop-control feature.
- Coordinate-first `pyautogui` automation as the preferred accessibility path.
- Free-form action success strings without structured verification.
- First-response-wins search without source quality, timestamp, or corroboration checks.

## Licence Boundary

The Mark-L README states: personal and non-commercial use only, CC BY-NC 4.0. The checkout contains no standalone `LICENSE` file. Nexi therefore treats Mark-L as a read-only architectural reference. Any potentially commercial Nexi Access implementation must be independently authored and must not include copied Mark-L code or assets.
