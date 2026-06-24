from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _write_wav(path: Path, pcm16: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Debug wake -> VAD command capture -> ASR without command_bus side effects.")
    parser.add_argument("--source", choices=["auto", "hotword", "double_clap", "hotkey"], default="auto")
    parser.add_argument("--timeout", type=float, default=30.0, help="Seconds to wait for wake in auto/hotword/double_clap mode")
    parser.add_argument("--output", default="data/wake_calibration/last_command.wav")
    args = parser.parse_args(argv)

    print("Jarvis wake-to-ASR debug")
    print("Wake detection is local. Groq ASR is called only after VAD accepts command speech.")
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"[WAKE_ASR] missing_audio_dependency reason={type(exc).__name__}")
        return 1

    from engine.audio_wake_pipeline import AudioWakePipeline, FRAME_SAMPLES, OpenWakeWordScorer, OWW_MODEL_PATH, OWW_PRETRAINED, POST_WAKE_DELAY_MS, SAMPLE_RATE

    scorer = None
    if args.source in {"auto", "hotword"}:
        try:
            scorer = OpenWakeWordScorer(model_path=OWW_MODEL_PATH, pretrained=OWW_PRETRAINED)
        except Exception as exc:
            print(f"[WAKE_ASR] hotword_scorer_failed reason={type(exc).__name__}")
            if args.source == "hotword":
                return 1

    transcripts: list[str] = []
    pipeline = AudioWakePipeline(wake_scorer=scorer, enable_clap=args.source in {"auto", "double_clap"}, on_command_text=transcripts.append)

    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, blocksize=FRAME_SAMPLES, dtype="int16") as stream:
            wake_source = args.source
            if args.source == "hotkey":
                input("Press Enter to simulate hotkey wake, then speak your command after LISTENING...")
            else:
                print(f"[WAKE_ASR] waiting_for_wake source={args.source} timeout={args.timeout}s")
                start = time.time()
                wake_source = ""
                while time.time() - start < args.timeout:
                    data, _overflow = stream.read(FRAME_SAMPLES)
                    result = pipeline.process_frame(bytes(data))
                    if result.get("wake"):
                        wake_source = result.get("source") or "hotword"
                        print(f"[WAKE_ASR] wake source={wake_source} reason={result.get('reason')} score={result.get('score', 0):.4f}")
                        break
                if not wake_source:
                    print("[WAKE_ASR] no_wake_detected")
                    return 2

            if POST_WAKE_DELAY_MS > 0:
                deadline = time.time() + POST_WAKE_DELAY_MS / 1000.0
                while time.time() < deadline:
                    stream.read(FRAME_SAMPLES)
                print(f"[WAKE_ASR] post_wake_delay_ms={POST_WAKE_DELAY_MS}")

            print("[WAKE_ASR] LISTENING. Speak your command now.")

            def next_frame():
                data, _overflow = stream.read(FRAME_SAMPLES)
                return bytes(data)

            audio = pipeline.capture_command(next_frame, source=wake_source)
            out = ROOT / args.output
            _write_wav(out, audio, SAMPLE_RATE)
            print(f"[WAKE_ASR] saved_command_wav={out}")
            transcript = pipeline.emit_command(audio, source=wake_source)
            if transcript:
                print(f"[WAKE_ASR] transcript={transcript}")
                return 0
            stats = pipeline._last_capture_stats
            print(f"[WAKE_ASR] empty_transcript_or_skipped stats={stats}")
            return 2
    except KeyboardInterrupt:
        print("[WAKE_ASR] stopped_by_user")
        return 2
    except Exception as exc:
        print(f"[WAKE_ASR] failed reason={type(exc).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
