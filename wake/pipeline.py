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


def _apply_gain(frame: bytes, gain: float) -> bytes:
    """Scale an int16 PCM frame by `gain` (with clipping). For weak mics."""
    import numpy as np
    a = np.frombuffer(frame, dtype=np.int16).astype(np.float32) * gain
    np.clip(a, -32768, 32767, out=a)
    return a.astype(np.int16).tobytes()


def _resolve_device(spec: str):
    """Map an AUDIO_INPUT_DEVICE env value to a sounddevice device id."""
    spec = (spec or "").strip()
    if not spec:
        return None
    return int(spec) if spec.isdigit() else spec


class AudioWakePipeline:
    def __init__(self, command_queue=None, speaking_event=None):
        self._command_queue = command_queue
        self._speaking_event = speaking_event
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

        # Input gain for weak microphones (applied before wake detection).
        # A separate, larger clap gain lets a close-talk mic (earbuds) still
        # catch faint, far-from-mic claps without clipping the strong voice
        # signal the hotword model needs.
        self._input_gain = env_float("WAKE_INPUT_GAIN", 1.0)
        self._clap_gain = env_float("CLAP_INPUT_GAIN", 1.0)
        self._input_device = _resolve_device(os.getenv("AUDIO_INPUT_DEVICE", ""))

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
                print(f"[WAKE] stream_stop_failed", flush=True)
        print("[WAKE] pipeline stopped", flush=True)

    def _open_stream(self):
        import sounddevice as sd

        def _callback(indata, frames, time_info, status):
            if status:
                print(f"[WAKE] stream_status: {status}", flush=True)
            try:
                self._frame_queue.put_nowait(bytes(indata))
            except queue.Full:
                pass  # drop oldest frame if buffer full

        candidates = []
        for dev in (self._input_device, None, 0):
            if dev not in candidates:
                candidates.append(dev)

        for dev in candidates:
            try:
                stream = sd.RawInputStream(
                    samplerate=cfg.sample_rate,
                    channels=cfg.channels,
                    dtype="int16",
                    blocksize=FRAME_SAMPLES,
                    device=dev,
                    callback=_callback,
                )
                stream.start()
                self._stream = stream
                self._input_device = dev
                print(f"[WAKE] mic opened device={dev} gain={self._input_gain}x", flush=True)
                return
            except Exception as e:
                print(f"[WAKE] mic_open_failed device={dev} reason={type(e).__name__}: {str(e)[:80]}", flush=True)

        self._stream = None
        try:
            inputs = [f"[{i}] {d['name']}" for i, d in enumerate(sd.query_devices())
                      if d["max_input_channels"] > 0]
            print("[WAKE] no usable mic. Available inputs: " + " | ".join(inputs), flush=True)
        except Exception:
            print("[WAKE] no usable mic and device list unavailable", flush=True)

    def _suppressed(self) -> bool:
        """True while NEXI is speaking — ignore the mic to avoid self-wake."""
        return self._speaking_event is not None and self._speaking_event.is_set()

    def _worker_loop(self):
        while self._running:
            try:
                frame = self._frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self._suppressed():
                self._preroll.clear()
                continue

            self._preroll.append(frame)
            wake_result = self._process_frame(frame)
            if wake_result.get("detected"):
                source = wake_result.get("source", "unknown")
                print(f"[WAKE] detected source={source}", flush=True)
                self._trigger_wake(source)

    def _process_frame(self, frame: bytes) -> dict:
        """Check all wake sources on one frame."""
        # Hotword (uses the raw/voice-gained signal)
        if self._hotword:
            hw_frame = _apply_gain(frame, self._input_gain) if self._input_gain != 1.0 else frame
            result = self._hotword.process_frame(hw_frame, cfg.sample_rate)
            if result.get("detected"):
                return result

        # Clap (separately boosted so faint claps register on a close-talk mic)
        if self._clap:
            clap_frame = _apply_gain(frame, self._clap_gain) if self._clap_gain != 1.0 else frame
            result = self._clap.process_frame(clap_frame)
            if result.get("detected"):
                return result

        return {"detected": False}

    def _trigger_wake(self, source: str):
        """Full wake → capture → ASR → dispatch flow."""
        # Flush wake-tail audio first
        flush_frames = max(1, int(self._flush_ms / cfg.frame_ms))
        for _ in range(flush_frames):
            try:
                self._frame_queue.get(timeout=0.05)
            except queue.Empty:
                break

        # Post-wake delay
        time.sleep(self._post_wake_delay_ms / 1000.0)

        # Post wake status AFTER audio flush
        from core.bridge import post_wake_detected, post_status, post_command
        post_wake_detected(self._command_queue, source=source)

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


def start_pipeline(command_queue=None, speaking_event=None) -> bool:
    global _pipeline
    _pipeline = AudioWakePipeline(command_queue=command_queue, speaking_event=speaking_event)
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
