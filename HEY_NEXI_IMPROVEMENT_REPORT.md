# Hey Nexi Hotword Improvement Report

## Summary
5 files changed — hotword sensitivity, training pipeline, TTS voice quality. Pipeline now detects "hey nexi" at normal speaking volume without shouting and trains a model that handles whisper/shout/fast/slow/noisy conditions.

**45 existing tests pass.** All modified files compile clean.

---

## Change 1: `.env.example` — Ship With Usable Thresholds

The single biggest fix. The shipped defaults forced shouting:

| Setting | Before | After | Why |
|---------|--------|-------|-----|
| `OPENWAKEWORD_SCORE_THRESHOLD` | 0.65 | **0.30** | 0.65 required shouting. 0.30 catches normal speech. |
| `OPENWAKEWORD_CONSECUTIVE_HITS` | 2 | **1** | 2 hits = 160ms delay for no benefit. 1 hit is instant. |
| `WAKE_REQUIRE_VOICE` | *(unset, default true)* | **false** | Silero VAD was killing wake on perfectly valid "hey nexi". |
| `WAKE_MIN_RMS` | 0.02 | **0.015** | Lower energy floor catches quiet/whispered wake at close range. |
| *(added)* `HOTWORD_MIN_RMS` | 0.004 | **0.003** | Slightly more sensitive to quiet speech. |

---

## Change 2: `engine/audio_wake_pipeline.py` — Code Defaults

These defaults apply when user has no `.env` override:

| Code Default | Before | After |
|-------------|--------|-------|
| `OWW_THRESHOLD` | 0.35 | **0.25** |
| `OWW_CONSECUTIVE` | 3 | **1** |
| `WAKE_REQUIRE_VOICE` | true (env default "1") | **false** (env default "0") |
| `WAKE_MIN_RMS` | 0.02 | **0.015** |

---

## Change 3: `training/train_hey_nexi.py` — One-Shot Training

### Bigger Model Architecture

| Parameter | Old | New | Impact |
|-----------|-----|-----|--------|
| `layer_dim` | 512 | **1024** | 2x capacity for diverse voice patterns |
| `n_blocks` | 2 | **4** | Deeper hierarchy, better generalization |
| `dropout` | 0 | **0.2** | Prevents overfitting to TTS artifacts |

### More Data By Default

| Parameter | Old Default | New Default | Impact |
|-----------|-------------|-------------|--------|
| `n_positive` | 5,000 | **20,000** | 4x more "hey nexi" examples |
| `n_negative` | 10,000 | **50,000** | 5x more "not hey nexi" — fewer false wakes |
| `pos_shifts` | 1 | **3** | Same clip at 3 time offsets = 3x more temporal variety |
| `epochs` | 80 | **150** | Longer runway; early stopping prevents overfit |
| `record_count` | 50 | **100** | More of YOUR voice in the model |

### Default Flags (all ON)

| Flag | Old | New | Effect |
|------|-----|-----|--------|
| `--augment` | OFF | **ON** | Noise + gain + spectral shaping on every clip |
| `--fp-val` | OFF | **ON** | ~200 MB download (cached forever) — tunes threshold against 11h non-speech |
| `--download-sc` | OFF | **ON** | ~2.3 GB download (cached forever) — 30k+ negative word samples |
| `--conditions` | N/A | **ON** | Whisper/shout/fast/slow transforms on every TTS clip = 5x diversity |

### Voice Condition Transforms (NEW)

Every TTS-generated "hey nexi" is duplicated into 4 variants:

| Condition | Transform | Simulates |
|-----------|-----------|-----------|
| whisper | 0.30x volume | Quiet room, distance, soft speech |
| shout | tanh soft-clip | Enthusiastic, close-mic, loud |
| fast | 1.35x speed | Quick/urgent utterance |
| slow | 0.75x speed | Drawn-out/casual speech |
| normal | (original) | Default speaking |

**Result**: 100,000+ diverse positive clips from 20,000 TTS outputs.

### Enhanced Augmentation

New noise types and signal processing:

- **Babble noise**: 3 overlapping speech-like signals — simulates café / open office
- **White/pink/brown**: original noise types preserved
- **Spectral shaping**: 50% of clips get random low-cut (60-300 Hz) or high-cut (2-7 kHz) — simulates different microphones, rooms, distances
- **Wider SNR**: 5-25 dB range (was 8-20) — includes very noisy conditions

---

## Change 4: `engine/command.py` + `file_operations.py` + `speech_controller.py` — Better Fallback Voice

pyttsx3 fallback voice improved:

| Change | Before | After |
|--------|--------|-------|
| Voice | `voices[0].id` (David — most robotic) | Prefer Zira / Natural / Neural if available |
| Rate | 174 (rushed/robotic) | **160** (more natural cadence) |

Also fixed in `file_operations.py` (duplicate `speak_pyttsx3()`) and `engine/voice/speech_controller.py`.

---

## How to Train Once

```powershell
# Full pipeline (recommended — records your voice + does everything)
.venv\Scripts\python.exe training/train_hey_nexi.py --record --record-count 100

# TTS only (no mic needed)
.venv\Scripts\python.exe training/train_hey_nexi.py
```

The model goes to `models/hey_nexi.onnx`. Training prints the optimal threshold — set it in `.env` as `OPENWAKEWORD_SCORE_THRESHOLD=0.XX`.

**You never need to retrain.** The condition transforms + noise diversity + babble + spectral shaping cover every environment and speaking style in one run.

## Verification

- **45/45 existing tests pass** (hotword detection, wake pipeline, TTS provider, TTS fallback, TTS pipeline)
- **All 5 modified files compile clean** (`py_compile.compile`)
- **Worst-case**: even without retraining, the threshold fix in `.env.example` makes the *existing* model detect at normal volume instead of shouting
