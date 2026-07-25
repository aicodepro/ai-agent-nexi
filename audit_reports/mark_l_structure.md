# Mark-L Structure Audit

Audit basis: local checkout at `C:\Users\marke\AppData\Local\Temp\opencode\mark-l` on 2026-07-23.

## Runtime Shape

Mark-L is a Python desktop assistant centered on one large `main.py`. That file owns the Gemini Live session, audio I/O, static tool declarations, tool dispatch, proactive behavior, memory updates, and UI coordination. The design is simple to follow but concentrates authority in one module.

Primary areas:

- `main.py`: Gemini Live audio session and the static tool catalogue.
- `ui.py`: PyQt6 HUD and content display.
- `actions/`: direct browser, desktop, file, messaging, monitoring, and search implementations.
- `core/stt.py`: local faster-whisper and Vosk adapters.
- `core/tts.py`: Edge TTS, Kokoro, and ElevenLabs adapters plus playback.
- `core/llm_client.py`: Ollama and OpenAI-compatible local model client.
- `memory/memory_manager.py`: bounded JSON identity, preference, project, relationship, wish, note, and short session storage.

## Authority Model

Mark-L does not expose an explicit router/session/response authority split. Gemini Live receives a static list of tool declarations and decides when to call tools. `main.py` is therefore the effective conversation, routing, and response authority.

The action modules execute operations directly. Many desktop operations use `pyautogui`; browser operations use a mixture of normal-browser launch and automation. Results are primarily human-readable strings rather than typed execution receipts with independent verification.

## Useful Patterns

- Web search has distinct `search`, `news`, `research`, `price`, and `compare` modes.
- Search uses grounded Gemini first and DuckDuckGo fallback; news starts both providers concurrently.
- Memory is bounded and organized by user-oriented categories.
- Session summaries are consumed after a briefing so they do not repeat forever.
- Local LLM startup includes health checks, model availability checks, warmup, and provider normalization.
- Vision requests acknowledge the user before a slower capture/analysis operation.
- Faster-whisper uses VAD filtering and disables previous-text conditioning to reduce hallucination carry-over.

## Risks And Limitations

- `main.py` is a large shared authority and static tool catalogue, making policy and lifecycle behavior difficult to isolate.
- API credentials are loaded from `config/api_keys.json`, not an OS credential store.
- `main.py` globally monkey-patches `subprocess.Popen` on Windows.
- `core/tts.py` can install/upgrade packages at runtime, which is unsuitable for Nexi's guarded execution model.
- Direct `pyautogui` coordinates and focused-field typing are not accessibility-first or independently verifiable.
- Search returns free-form text. It does not provide Nexi's required structured citations, retrieval timestamps, or claim-to-source mapping.
- The news race returns the first sufficiently long result, not the best corroborated result.
- README claims broad capabilities but the repository has no comparable acceptance harness proving all advertised paths.

## Conclusion

Mark-L is most valuable as a product-pattern reference for search modes, proactive briefings, bounded memory, local model health checks, and immediate acknowledgement. It is not suitable as Nexi's runtime authority or as a source for direct code copying.
