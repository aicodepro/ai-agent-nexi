# Proposal: the "NEXI Voice Data Factory" — training the wake word on many AI voices

## The reframe (important)
The pipeline we already have uses **Piper**, which *is* an AI/neural TTS — so the
current samples are already AI-generated. The real upgrade you want is **diversity
of AI voices + conditions**: not one TTS voice, but hundreds of speakers, accents,
ages, speeds, pitches, emotions, whispered and shouted — plus voice cloning — so
the "hey nexi" model recognizes the phrase from *anyone*, in *any* condition, and
still generalizes to REAL human voices. That last part is the whole game.

## The system (a repeatable, re-runnable pipeline)
Think of it as a factory with 7 stations. Each is a small module; the whole thing
re-runs so the model keeps improving over time.

1. **Multi-engine generation.** Orchestrate several *open-source* TTS engines, not
   one: **Piper** (fast, many voices), **Coqui XTTS-v2** and **F5-TTS** (zero-shot
   voice cloning — this is the speaker multiplier), **StyleTTS2** (expressive),
   **Kokoro** (tiny + natural), **Parler-TTS** (describe the voice in text:
   "an old man, fast, gravelly"), **Bark** (emotion/non-verbal). Each engine's
   artifacts are different, so mixing engines stops the model overfitting to any
   one synthetic "sound."
2. **Voice multiplication (cloning).** Feed XTTS/F5 a *bank of reference speakers*
   (public sets: LibriTTS, VCTK, Common Voice) to clone hundreds of distinct
   voices saying "hey nexi." Optionally add an **RVC** voice-conversion pass to
   push clips toward natural human timbre (closes the synthetic→real gap).
3. **Style & condition variation.** Generate whispered / shouted / fast / slow /
   questioning / emotional variants (prosody controls + gain scaling). This is
   what gets you whisper-near-mic AND shout-across-room coverage.
4. **Quality gate (the key quality lever).** TTS sometimes mispronounces or clips.
   **Round-trip ASR verify** every clip: transcribe it (Whisper) and keep it only
   if the transcript says "hey nexi." Add energy/duration checks + near-duplicate
   removal. This alone lifts model quality more than raw sample count.
5. **Augmentation.** Mix in noise (MUSAN / AudioSet / DEMAND), room reverb (RIR
   datasets, near- and far-field), SpecAugment, gain/codec/telephony — across a
   range of SNRs. This is what makes it robust in crowds and noise.
6. **Hard negatives.** Generate confusable phrases the same way ("hey nexus",
   "hey lexi", "he needs", "hey next") + large negative corpora (openWakeWord's
   ACAV100M features, FMA music) so it doesn't false-fire.
7. **Train + evaluate + iterate.** Feed openWakeWord training; then score on a
   **per-condition test set** (quiet / noisy / whisper / shout / accent) using
   false-reject-rate vs false-accepts-per-hour. Re-run with more voices/conditions
   until the numbers are good.

## The three things that make or break it (from the research)
- **Licensing.** Cloud TTS (ElevenLabs, OpenAI, Azure) often *restricts using
  output to train models*. So build the training set from **open-source TTS**
  (Piper/XTTS/F5/StyleTTS2/Kokoro/Bark — permissive licenses). Use cloud voices,
  if at all, only for a small eval slice.
- **Synthetic→real gap.** A model trained on *only* TTS can learn TTS fingerprints
  and fail on real people. Mitigate with: many engines (no single fingerprint) +
  heavy augmentation + an RVC naturalness pass + **a handful of REAL "hey nexi"
  recordings** from you and your family folded in.
- **Quality over quantity.** 20k ASR-verified, diverse, augmented clips beat 100k
  raw ones. The round-trip ASR gate (station 4) is the highest-ROI idea here.

## Where it lives in NEXI
A new `engine/wake_training/` (or `scripts/voice_factory/`) package — one module
per station, a `factory.py` that runs them in order, and a YAML that lists which
engines/voices/conditions to use. Output: `models/hey_nexi.onnx` + an eval report.
Re-runnable, so it becomes a permanent capability, not a one-off.

## Ranked ideas to pursue after the first build
1. **Round-trip ASR-verified generation** — biggest quality lever, build first.
2. **RVC voice-conversion layer** — turns synthetic clips human, closes the gap.
3. **Real-user personalization** — capture *your* + family's real "hey nexi" and
   few-shot fine-tune, so it's tuned to your household specifically.
4. **Continuous hard-negative mining** — log real false-fires in production, feed
   them back as negatives, auto-retrain. This is a self-improving loop and fits
   NEXI's autonomy/Forge direction.
5. **Per-condition eval harness as a deploy gate** — never ship a model that
   regresses whisper/shout/noise scores.
6. **Reuse the voice stack for NEXI's OWN voice** — the same multi-engine +
   emotion TTS can later give Nexi an expressive, human-sounding *speaking* voice
   (directly serves "feel like a real human").

## Honest note
This is a real build (several engines, GPU generation, augmentation, eval), best
done on a GPU box/Colab, iterated over days — not a one-afternoon script. The
round-trip-ASR + multi-engine + augmentation core gets you 80% of the value; the
cloning/RVC/personalization layers are the polish.
