# Training a real "hey nexi" wake word

## Why
The current `models/hey_nexi.onnx` is a **badly-trained** openWakeWord model — it
returns `score≈1.0` on *everything*, including silence, so it isn't detecting the
phrase at all (it's just an energy gate). A neural wake model can only be trained
offline (it needs a dataset + GPU), so this is done once, outside NEXI, and the
resulting `hey_nexi.onnx` is dropped back in.

Good news: **you don't record anything by hand.** openWakeWord trains from
*synthetic* speech (TTS) + noise augmentation + prebuilt negative data.

## Easiest path — openWakeWord's official Colab (recommended)
1. Open openWakeWord's **automatic model training** notebook:
   `https://github.com/dscripka/openWakeWord` → `notebooks/automatic_model_training.ipynb`
   (there's a "Open in Colab" badge). Use a **GPU runtime** (Runtime → Change runtime type → GPU).
2. In the config cell, set:
   ```python
   target_word    = "hey nexi"
   model_name     = "hey_nexi"
   # more positives + more training steps = better accuracy / fewer false wakes:
   number_of_examples          = 40000      # synthetic "hey nexi" clips
   number_of_training_steps    = 50000
   false_positive_validation_data_path = "validation_set_features.npy"  # provided by the notebook
   ```
   The notebook uses **piper-sample-generator** to synthesize thousands of "hey
   nexi" utterances across many voices/speeds/pitches, augments them with room
   noise + reverb (this is what makes it robust in crowds/shouting), mixes in the
   provided negative features (so it stays quiet on non-wake audio), trains, and
   **exports `hey_nexi.onnx`**.
3. Download the resulting `hey_nexi.onnx`.

## Put it back into NEXI
1. Replace the file: `E:\ai-agnet-nexi\models\hey_nexi.onnx` with your trained one.
2. Make sure `.env` points at it (this is already how it loads):
   ```
   OPENWAKEWORD_MODEL_PATH=models/hey_nexi.onnx
   OPENWAKEWORD_SCORE_THRESHOLD=0.5     # start here; raise if it false-fires
   OPENWAKEWORD_CONSECUTIVE_HITS=2      # frames required; raise for stricter
   ```
3. Restart NEXI.

## Verify it's actually trained (not the broken one)
Watch the `[HOTWORD]` log lines:
- **Silence / room noise** → `score≈0.00` (the broken model showed `1.0000` here — that's the tell).
- **You say "hey nexi"** → `score` jumps to `~0.8–0.99` → `[WAKE] detected`.
If silence still shows `1.0`, the old model is still loaded (check the `.env` path).

## Tuning for your room
- Too many false wakes → raise `OPENWAKEWORD_SCORE_THRESHOLD` (0.5 → 0.6–0.7) and/or `OPENWAKEWORD_CONSECUTIVE_HITS` (2 → 3).
- Misses your real "hey nexi" → lower the threshold, or retrain with more `number_of_examples`.
- Whisper support: train with quieter augmented samples; keep `NEXI_WAKE_MIN_RMS` low (~0.012) so quiet-but-clear "hey nexi" still passes the energy floor.

## Notes
- Follow the notebook's *current* cells for exact API — openWakeWord updates its
  training interface; the parameter names above are the stable ones but defer to
  the notebook if they differ.
- Local (non-Colab) training needs: Python 3.10+, PyTorch w/ CUDA,
  `pip install openwakeword piper-phonemize`, plus piper-sample-generator. Colab
  is far easier for a one-off.
- Once you have a good `hey_nexi.onnx`, the energy/voice heuristics we added
  (`NEXI_WAKE_MIN_RMS`, the Silero voice-gate) become a *secondary* safety net —
  the trained phrase model does the real "is this for Nexi?" gating.
