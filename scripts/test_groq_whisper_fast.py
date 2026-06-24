"""Direct Groq Whisper smoke test.

Loads .env. If GROQ_API_KEY is configured, transmits 1 second of silence
to Groq and prints a safe preview of the transcript (likely empty for
silence — proves the round-trip without requiring a microphone).

Never prints GROQ_API_KEY or auth headers. Exits non-zero only on a code
crash, not on a provider error.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    key = (os.getenv("GROQ_API_KEY", "") or "").strip()
    if not key:
        print("[SMOKE] GROQ_API_KEY not configured; skipping live call.")
        # Still exercise the WAV builder to prove the module imports.
        try:
            from engine.groq_asr import pcm_float32_to_wav_bytes
            wav = pcm_float32_to_wav_bytes(b"\x00\x00" * 1600, sample_rate=16000)
            print(f"[SMOKE] wav_bytes_built len={len(wav)}")
            return 0
        except Exception as e:
            print(f"[SMOKE] wav builder failed: {type(e).__name__}: {e}")
            return 1

    try:
        from engine.groq_asr import pcm_float32_to_wav_bytes, transcribe_audio_bytes
    except Exception as e:
        print(f"[SMOKE] import failed: {type(e).__name__}: {e}")
        return 1

    # 1 second of silence at 16 kHz mono int16 == 32 000 bytes.
    pcm = b"\x00\x00" * 16000
    wav = pcm_float32_to_wav_bytes(pcm, sample_rate=16000)
    print(f"[SMOKE] wav_bytes_built len={len(wav)}")

    try:
        text = transcribe_audio_bytes(wav, filename="silence.wav")
    except Exception as e:
        print(f"[SMOKE] transcribe crashed: {type(e).__name__}: {e}")
        return 1

    preview = text[:60].replace("\n", " ")
    print(f"[SMOKE] transcript_chars={len(text)} preview={preview!r}")

    # Sanity: never leak the key.
    if key and key in (text or ""):
        print("[SMOKE] WARNING: api key appeared in transcript; suppressed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
