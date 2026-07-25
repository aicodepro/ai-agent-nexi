# NEXI — Microphone Auto-Selection

Pipeline rate: **16000 Hz mono**. Mode: `AUDIO_INPUT_DEVICE=auto`. Re-evaluated on every launch.

## 1. Device Dashboard

| Idx | Device | Opens @16kHz | Score | Rank |
|----|--------|:---:|:---:|------|
| 2 | Headset (Phantom 550) | ✅ | 90 | Best |
| 8 | Headset (Phantom 550) | ✅ | 90 | Second-Best |
| 15 | Headset (Phantom 550) | ✅ | 90 | #3 |
| 1 | Microphone Array (Intel® Smart  | ✅ | 70 | #4 |
| 7 | Microphone Array (Intel® Smart Sound Technology  | ✅ | 70 | #5 |
| 0 | Microsoft Sound Mapper - Input | ❌ | -1000 | excluded |
| 6 | Primary Sound Capture Driver | ❌ | -1000 | excluded |
| 14 | Microphone Array (Intel® Smart Sound Technology  | ❌ | -1000 | excluded |
| 16 | Microphone Array 1 (Intel® Smart Sound Technolog | ❌ | -1000 | excluded |
| 17 | Microphone Array 2 (Intel® Smart Sound Technolog | ❌ | -1000 | excluded |
| 18 | Microphone Array 3 (Intel® Smart Sound Technolog | ❌ | -1000 | excluded |
| 21 | PC Speaker (Realtek HD Audio output with SST) | ❌ | -1000 | excluded |
| 22 | Stereo Mix (Realtek HD Audio Stereo input) | ❌ | -1000 | excluded |
| 25 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |
| 27 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |
| 30 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |
| 32 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |
| 35 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |
| 40 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |
| 42 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |
| 46 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |
| 49 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |
| 52 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |
| 55 | Headset (@System32\drivers\bthhfenum.sys,#2;%1 H | ❌ | -1000 | excluded |

## 2. Selection Rationale
- **Device:** `Headset (Phantom 550)`  (index **2**)
- **Score:** 90 — highest-scoring device that opens at 16 kHz mono; headset mics are preferred (close-talk = better SNR) over the built-in array.
- **Calibration:** none required — opens directly at the pipeline's 16 kHz/mono/float32 contract.

## 3. Fallback Plan
- **Second-Best:** `Headset (Phantom 550)` (index 8, score 90).
- **Promoted when:** the selected device fails to open at launch (stream-open fallback), or is unplugged before the next launch (re-evaluation picks the new best). Final fallback is the OS default input.

## Config knobs
- `AUDIO_INPUT_DEVICE=auto` — enable auto-selection (or set a numeric index / device name to pin one).
- `NEXI_MIC_PREFER_HEADSET=true` — set `false` to prefer the built-in array instead.
