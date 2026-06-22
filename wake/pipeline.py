"""Audio wake pipeline — mic → wake detection → VAD capture → ASR → bridge."""

import os
import queue
import struct
import threading
import time
from collections import deque
from core.config import cfg, env_int, env_float

# Pipeline state
_pipeline = None
_last_error = ""

# Audio constants
FRAME_SAMPLES = int(cfg.sample_rate * cfg.frame_ms / 1000)
FRAME_BYTES = FRAME_SAMPLES * 2  # 16-bit PCM


class AudioWakePipeline:
    def __init__(self, command_queue=None):
        self._command_queue = command_queue
        self._running = False
        self._frame_queue = queue.Queue(maxsize=200)
        self._worker_thread = None
        self._stream = None

        # Wake detectors
        self._hotword = None
        self._clap = None

        # VAD
        self._vad = None

        # Capture settings
        self._listen_timeout = env_int("COMMAND_LISTEN_TIMEOUT_SECONDS", 8)
        self._silence_end_ms = env_int("VAD_SILENCE_END_MS", 900)
        self._min_speech_ms = env_int("VAD_MIN_SPEECH_MS", 300)
        self._preroll_ms = env_int("VAD_PREROLL_MS", 400)
        self._post_wake_delay_ms = env_int("POST_WAKE_DELAY_MS", 200)
        self._flush_ms = env_int("WAKE_FLUSH_AUDIO_MS", 300)

        # Preroll buffer
        preroll_frames = max(1, int(self._preroll_ms / cfg.frame_ms))
        self._preroll = deque(maxlen=preroll_frames)

    def start(self) -> bool:
        global _last_error
        try:
            # Init hotword
            if cfg.hotword_enabled:
                from wake.hotword import HotwordDetector
                self._hotword = HotwordDetector()
                if not self._hotword.load():
                    print("[WAKE] hotword load failed, continuing without", flush=True)
                    self._hotword = None

            # Init clap
            if cfg.clap_enabled:
                from wake.clap import ClapDetector
                self._clap = ClapDetector(sample_rate=cfg.sample_rate)

            # Init VAD
            from wake.vad import create_vad
            self._vad = create_vad()

            # Open mic stream
            self._open_stream()
            if not self._stream:
                _last_error = "mic_open_failed"
                return False

            # Start worker
            self._running = True
            self._worker_thread = threading.Thread(target=self._worker_loop,
                                                   daemon=True, name="wake-worker")
            self._worker_thread.start()
            print(f"[WAKE] pipeline started rate={cfg.sample_rate} frame_ms={cfg.frame_ms}", flush=True)
            return True

        except Exception as e:
            _last_error = str(e)
            print(f"[WAKE] start_failed reason={type(e).__name__}", flush=True)
            return False

    def stop(self):
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        print("[WAKE] pipeline stopped", flush=True)

    def _open_stream(self):
        try:
            import sounddevice as sd
            def _callback(indata, frames, time_info, status):
                if status:
                    pass  # ignore overflow
                self._frame_queue.put_nowait(bytes(indata))

            self._stream = sd.RawInputStream(
                samplerate=cfg.sample_rate,
                channels=cfg.channels,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
                callback=_callback,
            )
            self._stream.start()
        except Exception as e:
            print(f"[WAKE] mic_failed reason={type(e).__name__}", flush=True)
            self._stream = None

    def _worker_loop(self):
        while self._running:
            try:
                frame = self._frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            self._preroll.append(frame)
            wake_result = self._process_frame(frame)
            if wake_result.get("detected"):
                source = wake_result.get("source", "unknown")
                print(f"[WAKE] detected source={source}", flush=True)
                self._trigger_wake(source)

    def _process_frame(self, frame: bytes) -> dict:
        """Check all wake sources on one frame."""
        # Hotword
        if self._hotword:
            result = self._hotword.process_frame(frame, cfg.sample_rate)
            if result.get("detected"):
                return result

        # Clap
        if self._clap:
            result = self._clap.process_frame(frame)
            if result.get("detected"):
                return result

        return {"detected": False}

    def _trigger_wake(self, source: str):
        """Full wake → capture → ASR → dispatch flow."""
        # Post wake status
        from core.bridge import post_wake_detected, post_status, post_command
        post_wake_detected(self._command_queue, source=source)

        # Flush wake-tail audio
        flush_frames = max(1, int(self._flush_ms / cfg.frame_ms))
        for _ in range(flush_frames):
            try:
                self._frame_queue.get(timeout=0.05)
            except queue.Empty:
                break

        # Post-wake delay
        time.sleep(self._post_wake_delay_ms / 1000.0)

        # Post listening status
        post_status(self._command_queue, "listening_started", source=source)

        # Capture command audio
        audio = self._capture_command()
        if not audio:
            post_status(self._command_queue, "sleeping", source=source)
            return

        # ASR
        post_status(self._command_queue, "recognising", source=source)
        from core.asr import pcm_float32_to_wav_bytes, transcribe
        wav_bytes = pcm_float32_to_wav_bytes(audio, cfg.sample_rate)
        transcript = transcribe(wav_bytes)

        if transcript.strip():
            print(f"[WAKE] transcript='{transcript[:60]}'", flush=True)
            post_command(self._command_queue, transcript, source=source)
        else:
            print("[WAKE] empty_transcript", flush=True)
            post_status(self._command_queue, "sleeping", source=source)

    def _capture_command(self) -> bytes:
        """Capture audio frames until VAD silence or timeout."""
        frames = []

        # Include preroll
        for frame in self._preroll:
            frames.append(frame)

        speech_detected = False
        speech_start = time.time()
        last_speech_time = time.time()
        timeout = self._listen_timeout

        while time.time() - speech_start < timeout:
            try:
                frame = self._frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            frames.append(frame)

            if self._vad and self._vad.is_speech(frame, cfg.sample_rate):
                speech_detected = True
                last_speech_time = time.time()
            elif speech_detected:
                silence_ms = (time.time() - last_speech_time) * 1000
                if silence_ms > self._silence_end_ms:
                    break

        if not speech_detected:
            return b""

        # Check minimum speech duration
        total_ms = len(frames) * cfg.frame_ms
        if total_ms < self._min_speech_ms:
            return b""

        return b"".join(frames)


def start_pipeline(command_queue=None) -> bool:
    global _pipeline
    _pipeline = AudioWakePipeline(command_queue=command_queue)
    return _pipeline.start()


def stop_pipeline():
    global _pipeline
    if _pipeline:
        _pipeline.stop()
        _pipeline = None


def is_running() -> bool:
    return _pipeline is not None and _pipeline._running


def get_last_error() -> str:
    return _last_error


def trigger_manual_wake():
    if _pipeline:
        _pipeline._trigger_wake("manual")
