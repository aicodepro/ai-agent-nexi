# Nexi And Mark-L Comparison

| Area | Nexi | Mark-L | Nexi Access Direction |
|---|---|---|---|
| Runtime | Multi-process Windows desktop assistant | Mostly monolithic Python/Gemini Live app | Keep Nexi process separation and explicit cross-process contracts |
| Voice lifecycle | Explicit wake/VAD/ASR/session/TTS states and leases | Gemini Live/audio loop centered in `main.py` | Keep Nexi authority; borrow only latency/product ideas |
| Routing | Rich but fragmented deterministic and semantic layers | Static Gemini tool list | Consolidate Nexi behind Router V3 using the registry |
| Tool catalogue | Typed risk, confirmation, slots, handler, aliases | Static declarations in `main.py` | Keep Nexi registry and generate manifests dynamically |
| Safety | Approval queue, sandbox policy, verified receipts | Mostly direct action calls | Keep Nexi deterministic safety gates |
| Desktop control | Guarded modules, still incomplete semantic UIA coverage | Broad `pyautogui` operations | Prefer UIA/semantic selectors; coordinates last |
| Web intelligence | Browser opening and page inspection, no evidence pipeline | Grounded Gemini plus DDG modes | Reimplement structured multi-provider retrieval with citations |
| Memory | Multiple newer memory subsystems | Small bounded JSON categories and consumed sessions | Borrow bounded/consumed concepts, add provenance and temporal fields |
| Local AI | Provider registry and fallbacks | Clear Ollama/OpenAI-compatible health and warmup | Adapt health/warmup behavior behind Nexi provider contracts |
| Response | Partial typed envelope and lifecycle guarantees | Direct Gemini/audio responses | Add one ResponseCoordinator over Nexi's existing response pieces |
| Spotify | Browser-level search only | No dedicated Spotify API integration found | Build PKCE Web API integration from official contracts |

## Decision

Nexi is the stronger base for safety, authority, Windows lifecycle, and verifiable execution. Mark-L demonstrates useful user-facing patterns but should not replace Nexi's architecture. Nexi Access should use a clean-room implementation of selected patterns and preserve Nexi's deterministic boundaries.
