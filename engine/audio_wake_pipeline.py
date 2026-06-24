# audio_wake_pipeline.py
#
# Batch 4 wake pipeline:
#   mic -> queue -> wake detection (openWakeWord + clap) -> VAD command capture
#        -> Groq Whisper -> runtime bridge/allCommands(transcript)
#
# Design rules (from the Batch 4 spec):
#   * one mic stream
#   * audio callback only pushes frames into a queue
#   * wake detector runs in worker thread (consumes queue)
#   * Groq transcription happens after wake + VAD stop
#   * allCommands() is called only by the UI process after transcript is ready
#   * graceful degradation on missing deps -> Nexi still starts
#
# Heavy deps (openwakeword, sounddevice, silero-vad, torch, numpy) are all
# lazy-imported. Missing deps surface as a single safe log line; the
# pipeline either falls back to a simpler strategy or refuses to start.

from __future__ import annotations

import os
import queue
import struct
import threading
import time
from collections import deque
from typing import Callable, Optional

from engine.wake_session_manager import get_session_manager, ignore_if_stale, start_session, finish_session


# ---- Config (env-overridable) ----
def _env(key: str, default: str) -> str:
    return (os.getenv(key, default) or default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _normalise_oww_name(name: str) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    if any(sep in value for sep in ("/", "\\")) or value.endswith((".onnx", ".tflite")):
        return value
    return value.replace("_", " ").lower()


def _normalise_oww_list(value: str) -> str:
    names = [_normalise_oww_name(item) for item in (value or "").split(",")]
    return ",".join(item for item in names if item)


def _clap_enabled_env() -> bool:
    if os.getenv("NEXI_CLAP_ENABLED") is not None:
        return _env_bool("NEXI_CLAP_ENABLED", False)
    return _env_bool("CLAP_DETECTION_ENABLED", False)


SAMPLE_RATE = _env_int("NEXI_WAKE_SAMPLE_RATE", _env_int("AUDIO_SAMPLE_RATE", 16000))
CHANNELS = _env_int("AUDIO_CHANNELS", 1)
WAKE_FRAME_MS = _env_int("NEXI_WAKE_FRAME_MS", 80)
FRAME_SAMPLES = _env_int("AUDIO_FRAME_SAMPLES", max(1, int(SAMPLE_RATE * WAKE_FRAME_MS / 1000)))
WAKE_BACKEND = _env("VOICE_WAKE_BACKEND", "openwakeword")
WAKE_ACTION = _env("WAKE_ACTION", "nexi_internal")
OWW_ENABLED = _env_bool("NEXI_HOTWORD_ENABLED", _env_bool("OPENWAKEWORD_ENABLED", True))
OWW_MODEL_PATH = _env("OPENWAKEWORD_MODEL_PATH", "")
OWW_PHRASES = _normalise_oww_list(_env("NEXI_HOTWORD_PHRASES", _env("NEXI_HOTWORD_PHRASE", "hey nexi,nexi")))
OWW_DEFAULT_MODEL = _normalise_oww_name((OWW_PHRASES.split(",") or ["hey nexi"])[0]) or "hey nexi"
OWW_PRETRAINED = _normalise_oww_list(
    _env(
        "OPENWAKEWORD_PRETRAINED_MODELS",
        OWW_DEFAULT_MODEL,
    )
)
OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.25)
OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 1)
WAKE_COOLDOWN_SECONDS = _env_float("WAKE_COOLDOWN_SECONDS", _env_int("NEXI_WAKE_COOLDOWN_MS", _env_int("OPENWAKEWORD_COOLDOWN_MS", 1500)) / 1000.0)
HOTWORD_MIN_RMS = _env_float("NEXI_HOTWORD_MIN_RMS", 0.003)
HOTWORD_RISING_EDGE_DELTA = _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.02)
AUDIO_INPUT_DEVICE = _env("AUDIO_INPUT_DEVICE", "")
WAKE_DEBUG = _env_bool("WAKE_DEBUG", False) or _env_bool("NEXI_WAKE_DEBUG", False) or _env_bool("OPENWAKEWORD_DEBUG", False)

VAD_BACKEND = _env("VAD_BACKEND", "silero")
VAD_MIN_SPEECH_MS = _env_int("VAD_MIN_SPEECH_MS", _env_int("NEXI_COMMAND_MIN_SPEECH_MS", 400))
VAD_SILENCE_END_MS = _env_int("VAD_SILENCE_END_MS", _env_int("ASR_SILENCE_TIMEOUT_MS", _env_int("NEXI_COMMAND_END_SILENCE_MS", 2200)))
COMMAND_LISTEN_TIMEOUT_SECONDS = _env_float(
    "COMMAND_LISTEN_TIMEOUT_SECONDS",
    _env_float("ASR_MAX_RECORD_SECONDS", _env_float("VAD_MAX_COMMAND_SECONDS", _env_float("NEXI_COMMAND_MAX_SPEECH_MS", 30000) / 1000.0)),
)
NO_SPEECH_TIMEOUT_SECONDS = _env_float("NEXI_COMMAND_NO_SPEECH_TIMEOUT_MS", 20000) / 1000.0
VAD_MAX_COMMAND_SECONDS = COMMAND_LISTEN_TIMEOUT_SECONDS
ASR_MAX_RECORD_SECONDS = _env_float("ASR_MAX_RECORD_SECONDS", VAD_MAX_COMMAND_SECONDS)
ASR_SILENCE_TIMEOUT_MS = _env_int("ASR_SILENCE_TIMEOUT_MS", VAD_SILENCE_END_MS)
ASR_FOLLOWUP_MAX_RECORD_SECONDS = _env_float("ASR_FOLLOWUP_MAX_RECORD_SECONDS", 4.0)
ASR_FOLLOWUP_SILENCE_TIMEOUT_MS = _env_int("ASR_FOLLOWUP_SILENCE_TIMEOUT_MS", 650)
ASR_MIN_AUDIO_MS = _env_int("ASR_MIN_AUDIO_MS", 1800)
POST_WAKE_DELAY_MS = _env_int("NEXI_POST_WAKE_DELAY_MS", _env_int("POST_WAKE_DELAY_MS", 1000))
VAD_MIN_RMS = _env_float("VAD_MIN_RMS", 0.015)
VAD_PREROLL_MS = _env_int("VAD_PREROLL_MS", 400)
WAKE_FLUSH_AUDIO_MS = _env_int("WAKE_FLUSH_AUDIO_MS", 500)


def _safe_log(msg: str) -> None:
    try:
        from engine.debug_trace import line
        line(msg)
    except Exception:
        print(msg, flush=True)


def _calc_rms_peak(frame_int16: bytes) -> tuple[float, float]:
    try:
        n = len(frame_int16) // 2
        if n <= 0:
            return 0.0, 0.0
        samples = struct.unpack(f"<{n}h", frame_int16)
        sum_sq = 0
        peak = 0
        for sample in samples:
            sum_sq += sample * sample
            abs_sample = abs(sample)
            if abs_sample > peak:
                peak = abs_sample
        return (sum_sq / n) ** 0.5 / 32768.0, peak / 32768.0
    except Exception:
        return 0.0, 0.0


# ---------------------------------------------------------------------------
# Wake scorers
# ---------------------------------------------------------------------------


class WakeScorer:
    """Abstract per-frame wake scorer. Returns float in [0, 1]."""

    name: str = "noop"

    def score(self, frame_int16: bytes) -> float:  # pragma: no cover
        return 0.0


# The concrete openWakeWord scorer lives in engine.openwakeword_scorer (fixed
# and verified: int16 input contract, loads the bundled hey_nexi model, fires
# ~0.99 on a real utterance). It duck-types WakeScorer (exposes .name / .score /
# .model_name / .get_debug_snapshot) so it drops straight into this pipeline.
from engine.openwakeword_scorer import OpenWakeWordScorer  # noqa: E402,F401


# ---------------------------------------------------------------------------
# VAD
# ---------------------------------------------------------------------------


class VAD:
    """Abstract VAD. Returns is_speech(frame_int16) -> bool."""

    name: str = "noop"

    def is_speech(self, frame_int16: bytes) -> bool:  # pragma: no cover
        return False


class EnergyVAD(VAD):
    """Calibrated energy-based VAD. Always available, no deps."""

    def __init__(self, rms_threshold: float = 0.012):
        self.name = "energy"
        self._rms_threshold = rms_threshold

    def is_speech(self, frame_int16: bytes) -> bool:
        try:
            import struct
            n = len(frame_int16) // 2
            if n == 0:
                return False
            samples = struct.unpack(f"<{n}h", frame_int16)
            sum_sq = sum(s * s for s in samples)
            rms = (sum_sq / n) ** 0.5 / 32768.0
            return rms >= self._rms_threshold
        except Exception:
            return False


class SileroVAD(VAD):
    """Silero VAD backed by the bundled openWakeWord ONNX model.

    Delegates to engine.silero_vad (onnxruntime + resources/models/
    silero_vad.onnx — already shipped with openWakeWord, so no extra
    dependency or download). That implementation has its own energy-based
    fallback, so construction here only fails if the module is truly absent.
    """

    def __init__(self):
        self.name = "silero"
        from engine.silero_vad import SileroVAD as _Impl  # bundled-ONNX impl
        self._impl = _Impl()

    def is_speech(self, frame_int16: bytes) -> bool:
        return self._impl.is_speech(frame_int16)

    def reset(self) -> None:
        try:
            self._impl.reset()
        except Exception:
            pass


def build_vad() -> VAD:
    """Try Silero first, fall back to EnergyVAD. Always returns something."""
    if VAD_BACKEND == "silero":
        try:
            return SileroVAD()
        except ImportError as e:
            _safe_log(f"[VAD] backend=energy fallback reason={e}")
    return EnergyVAD()


# ---------------------------------------------------------------------------
# ASR adapter
# ---------------------------------------------------------------------------


def _default_asr(audio_pcm16_bytes: bytes, sample_rate: int) -> str:
    """Default ASR: Groq Whisper. Lazy import."""
    try:
        from engine.groq_asr import pcm_float32_to_wav_bytes, transcribe_audio_bytes
    except Exception as e:
        _safe_log(f"[ASR] provider=groq failed reason={type(e).__name__}")
        return ""

    # `pcm_float32_to_wav_bytes` accepts raw PCM16 bytes too.
    wav = pcm_float32_to_wav_bytes(audio_pcm16_bytes, sample_rate=sample_rate)
    _save_asr_request_wav(wav)
    return transcribe_audio_bytes(wav)


def _save_asr_request_wav(audio_wav_bytes: bytes) -> None:
    try:
        from pathlib import Path
        artifacts_dir = Path("artifacts")
        artifacts_dir.mkdir(exist_ok=True)
        wav_path = artifacts_dir / "last_asr_request.wav"
        wav_path.write_bytes(audio_wav_bytes or b"")
        _safe_log(f"[ASR] request_audio_saved path={wav_path} bytes={len(audio_wav_bytes or b'')}")
    except Exception as e:
        _safe_log(f"[ASR] save_request_audio_failed reason={type(e).__name__}")


def _is_speaking() -> bool:
    """True while Nexi is producing TTS output (used for wake barge-in)."""
    try:
        from engine.interrupt_controller import is_speaking
        return bool(is_speaking())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class AudioWakePipeline:
    """Lazy, injectable wake pipeline.

    Public surface:
        start() / stop() / is_running
        process_frame(frame_int16) -> dict   # pure logic, used in tests
        emit_command(audio_bytes) -> None    # runs ASR + callback
    """

    def __init__(
        self,
        on_command_text: Optional[Callable[[str], None]] = None,
        *,
        wake_scorer: Optional[WakeScorer] = None,
        vad: Optional[VAD] = None,
        asr: Optional[Callable[[bytes, int], str]] = None,
        clock: Optional[Callable[[], float]] = None,
        enable_clap: Optional[bool] = None,
        command_queue=None,
    ):
        self._on_command_text = on_command_text
        self._command_queue = command_queue
        self._asr = asr or _default_asr
        self._clock = clock or time.time
        self._wake_scorer = wake_scorer  # built lazily in start() if None
        self._vad = vad  # built lazily in start() if None

        self._enable_clap = enable_clap
        self._frame_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=256)
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._stream = None
        self._last_start_error = ""
        self._capture_lock = threading.Lock()
        self._audio_received_logged = False
        self._last_capture_stats: dict = {}

        # Per-frame wake state
        self._consecutive_hits = 0
        self._last_wake_at = 0.0
        self._prev_hotword_score = 0.0

        try:
            from engine.wake_orchestrator import WakeOrchestrator
            self._wake_orch = WakeOrchestrator({"clock": self._clock})
        except Exception:
            self._wake_orch = None

        # Pre-roll
        preroll_frames = max(
            1, int((VAD_PREROLL_MS / 1000.0) * SAMPLE_RATE / FRAME_SAMPLES)
        )
        self._preroll: "deque[bytes]" = deque(maxlen=preroll_frames)

        # Internal wake signal bus (replaces keyboard injection)
        self._wake_signal_bus: Optional[any] = None
        try:
            from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal
            self._wake_signal_bus = InternalWakeSignalBus(queue=command_queue, debug=WAKE_DEBUG)
            self._WakeSignal = WakeSignal
        except Exception:
            self._wake_signal_bus = None

        # Clap state (via backend manager; DSP is the safe default)
        self._clap_manager = None

        try:
            from engine.nexi_wake_controller import set_wake_queue
            set_wake_queue(command_queue)
        except Exception:
            pass

    @property
    def last_start_error(self) -> str:
        return self._last_start_error

    # ---- defaults ----

    @staticmethod
    def _default_command_handler(text: str) -> None:
        """Fallback handler when no bridge queue is provided.

        This calls allCommands directly — which works in unit tests and
        single-process debug scripts, but will fail in Process 2 where
        Eel JS functions are absent. In production run.py, run.py
        supplies a bridge callback instead so this code path is never
        reached.
        """
        if not text:
            return
        _safe_log("[VOICE] WARNING: direct allCommands call (no bridge queue)")
        try:
            from engine.command import allCommands
            allCommands(text)
        except Exception as e:
            _safe_log(f"[VOICE] allCommands failed reason={type(e).__name__}")

    # ---- public predicates ----

    @property
    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def is_clap_enabled(self) -> bool:
        if self._enable_clap is not None:
            return bool(self._enable_clap)
        return _clap_enabled_env() or self._clap_manager is not None

    # ---- pure per-frame logic (testable) ----

    def process_frame(self, frame_int16: bytes) -> dict:
        """Run one frame through the wake detectors.

        Returns a dict describing what happened. Used both in tests and
        in the live worker loop.
        """
        now = self._clock()
        result = {"wake": False, "source": None, "score": 0.0, "cooldown": False, "reason": "none"}

        # --- Barge-in: a wake word spoken WHILE Nexi is talking interrupts
        # the TTS instead of being captured as a command. Checked before the
        # detectors-paused gate because detectors are paused during "saying".
        if _is_speaking():
            score = self._wake_scorer.score(frame_int16) if self._wake_scorer is not None else 1.0
            if score >= OWW_THRESHOLD:
                self._consecutive_hits = 0
                self._prev_hotword_score = 0.0
                _safe_log(f"[BARGE_IN] hotword_during_speaking score={float(score):.3f}")
                try:
                    from engine.barge_in_manager import interrupt as _barge_in_interrupt
                    _barge_in_interrupt(source="hotword", reason="hotword_during_speaking")
                except Exception as e:
                    _safe_log(f"[BARGE_IN] interrupt_failed reason={type(e).__name__}")
                return {"wake": True, "source": "hotword", "reason": "hotword_during_speaking", "score": float(score)}
            return {"wake": False, "source": None, "reason": "speaking", "score": float(score)}

        if get_session_manager().are_detectors_paused():
            result["reason"] = "session_active"
            return result

        # Maintain pre-roll regardless of wake state.
        self._preroll.append(frame_int16)

        # 1. openWakeWord scoring (if configured)
        if self._wake_scorer is not None:
            score = self._wake_scorer.score(frame_int16)
            result["score"] = score
            scorer_name = getattr(self._wake_scorer, "name", "")
            if scorer_name == "openwakeword":
                rms, _peak = _calc_rms_peak(frame_int16)
                if rms < HOTWORD_MIN_RMS:
                    result["reason"] = f"low_rms_{rms:.5f}"
                    self._consecutive_hits = 0
                    self._prev_hotword_score = score
                    score = 0.0
                elif score >= OWW_THRESHOLD:
                    rising_edge = (score - self._prev_hotword_score) >= HOTWORD_RISING_EDGE_DELTA or self._prev_hotword_score == 0.0
                    self._prev_hotword_score = score
                    if not rising_edge:
                        result["reason"] = "no_rising_edge"
                        self._consecutive_hits = 0
                        score = 0.0
                else:
                    self._prev_hotword_score = score
            if score >= OWW_THRESHOLD:
                if get_session_manager().is_post_session_suppressed(now):
                    _safe_log(f"[WAKE_SUPPRESS] reason=post_session score={score:.4f} ignored=true")
                    self._consecutive_hits = 0
                    result["reason"] = "post_session_suppressed"
                    return result
                self._consecutive_hits += 1
                if self._consecutive_hits >= OWW_CONSECUTIVE:
                    self._consecutive_hits = 0
                    decision = self._evaluate_wake_candidate("hotword", True, score, now, "threshold")
                    result["cooldown"] = decision.cooldown_active
                    result["reason"] = decision.reason
                    if decision.should_wake:
                        result["wake"] = True
                        result["source"] = decision.source
                        return result
            else:
                self._consecutive_hits = 0

        # 2. Clap path (via backend manager: DSP primary, CLAP_NN fallback)
        if self.is_clap_enabled():
            try:
                from engine.clap_backend_manager import ClapBackendManager
                if self._clap_manager is None:
                    self._clap_manager = ClapBackendManager(clock=self._clock)
                clap_event = self._clap_manager.process_audio_chunk(frame_int16)
                if clap_event.get("clap") and not clap_event.get("wake"):
                    backend = clap_event.get("backend", "?")
                    gap = clap_event.get("gap_ms")
                    gap_text = "-" if gap is None else f"{gap:.0f}"
                    _safe_log(f"[CLAP] first_clap backend={backend} wake=false gap_ms={gap_text} amplitude={clap_event.get('amplitude', 0):.4f} reason={clap_event.get('reject_reason') or clap_event.get('reason', '')}")
                    _safe_log("[CLAP] waiting_for_second_clap")
                if clap_event.get("cooldown"):
                    _safe_log("[CLAP] cooldown active")
                    result["cooldown"] = True
                if clap_event.get("wake"):
                    backend = clap_event.get("backend", "?")
                    fallback = "fallback" if clap_event.get("fallback_used") else "primary"
                    confidence = max(0.0, min(1.0, float(clap_event.get("amplitude", 1.0) or 1.0)))
                    if get_session_manager().is_post_session_suppressed(now):
                        _safe_log(f"[WAKE_SUPPRESS] reason=post_session score={confidence:.4f} ignored=true")
                        result["reason"] = "post_session_suppressed"
                        return result
                    _safe_log(f"[CLAP] second_clap gap_ms={clap_event.get('gap_ms', '-')}")
                    _safe_log(f"[CLAP] double_clap_detected=true backend={backend}")
                    decision = self._evaluate_wake_candidate("double_clap", True, confidence, now, f"backend={backend}:{fallback}")
                    result["cooldown"] = decision.cooldown_active
                    result["reason"] = decision.reason
                    if decision.should_wake:
                        _safe_log(f"[CLAP] wake backend={backend} tier={fallback}")
                        result["wake"] = True
                        result["source"] = decision.source
                        return result
            except Exception as e:
                _safe_log(f"[CLAP] frame_eval failed reason={type(e).__name__}")

        return result

    def _evaluate_wake_candidate(self, source: str, detected: bool, confidence: float, timestamp: float, reason: str):
        try:
            from engine.wake_orchestrator import WakeSourceResult, WakeDecision
            if self._wake_orch is None:
                return WakeDecision(should_wake=bool(detected), source=source, reason=reason, confidence=confidence)
            result = WakeSourceResult(source=source, detected=detected, confidence=confidence, timestamp=timestamp, metadata={"reason": reason})
            return self._wake_orch.evaluate(result)
        except Exception:
            from engine.wake_orchestrator import WakeDecision
            return WakeDecision(should_wake=bool(detected), source=source, reason=reason, confidence=confidence)

    # ---- post-wake command capture (testable) ----

    def _post_status(self, status: str, source: str = "voice", text: str = "") -> None:
        if self._command_queue is None:
            return
        try:
            from engine.runtime_bridge import post_status
            post_status(self._command_queue, status, source=source, text=text)
        except Exception as e:
            _safe_log(f"[BRIDGE] status_post_failed reason={type(e).__name__}")

    def capture_command(self, frame_source: Callable[[], Optional[bytes]], source: str = "voice") -> bytes:
        """Capture frames after a wake event until VAD silence or max duration.

        `frame_source()` returns the next frame or None when no more frames
        are available. Pre-roll frames are prepended automatically so the
        first word isn't clipped.
        """
        vad = self._vad or build_vad()
        if self._vad is None:
            self._vad = vad

        frame_ms = max(1.0, (FRAME_SAMPLES / SAMPLE_RATE) * 1000.0)
        followup_capture = False
        try:
            from engine.clarification_manager import has_pending_clarification
            from engine.followup_manager import has_pending_followup
            followup_capture = has_pending_clarification() or has_pending_followup()
        except Exception:
            followup_capture = False
        max_seconds = ASR_FOLLOWUP_MAX_RECORD_SECONDS if followup_capture else ASR_MAX_RECORD_SECONDS
        silence_ms = ASR_FOLLOWUP_SILENCE_TIMEOUT_MS if followup_capture else ASR_SILENCE_TIMEOUT_MS
        max_frames = int((max_seconds * 1000.0) / frame_ms)
        silence_frames_target = max(1, int(silence_ms / frame_ms))
        min_speech_frames = max(1, int(VAD_MIN_SPEECH_MS / frame_ms))
        no_speech_frames = max(1, int(NO_SPEECH_TIMEOUT_SECONDS * 1000.0 / frame_ms))

        captured: list[bytes] = list(self._preroll)
        speech_started = False
        speech_frames = 0
        silence_frames = 0
        no_speech_frame_count = 0
        max_rms = 0.0

        self._post_status("waiting_for_speech", source=source)

        for _ in range(max_frames):
            frame = frame_source()
            if frame is None:
                break
            captured.append(frame)
            frame_rms, _frame_peak = _calc_rms_peak(frame)
            max_rms = max(max_rms, frame_rms)
            if vad.is_speech(frame):
                if not speech_started:
                    speech_started = True
                    _safe_log("[VAD] speech_started")
                    self._post_status("speech_started", source=source)
                speech_frames += 1
                silence_frames = 0
            else:
                if speech_started:
                    silence_frames += 1
                    # End on a natural trailing pause once speech has started.
                    # We do NOT require speech_frames >= min_speech_frames here:
                    # a short command ("open chrome") must still end promptly
                    # instead of recording until the max-duration ceiling. The
                    # min-speech requirement is enforced later as an ASR gate.
                    if silence_frames >= silence_frames_target:
                        break
                else:
                    no_speech_frame_count += 1
                    if no_speech_frame_count >= no_speech_frames:
                        break

        # min_speech_frames is retained for the ASR gate (see _check_vad_gates).
        _ = min_speech_frames

        duration_ms = int(len(captured) * frame_ms)
        speech_ms = int(speech_frames * frame_ms)
        _safe_log(f"[VAD] speech_ended duration_ms={duration_ms} speech_ms={speech_ms}")
        self._last_capture_stats = {
            "duration_ms": duration_ms,
            "speech_ms": speech_ms,
            "speech_started": speech_started,
            "speech_frames": speech_frames,
            "max_rms": max_rms,
            "source": source,
        }
        self._post_status("speech_ended", source=source)
        return b"".join(captured)

    def handle_recognized_text(self, text: str, source: str = "voice", session_id: str = "") -> bool:
        text = (text or "").strip()
        if not text:
            _safe_log("[RECOGNIZED] rejected reason=empty")
            return False
        preview = text[:60].replace("\n", " ")
        _safe_log(f"[RECOGNIZED] source={source} text={preview}")
        self._dispatch_transcript(text, source)
        return True

    def _dispatch_transcript(self, transcript: str, source: str) -> None:
        if self._command_queue is not None:
            try:
                from engine.runtime_bridge import post_command
                post_command(self._command_queue, transcript, source=source)
                return
            except Exception as e:
                _safe_log(f"[BRIDGE] error reason={type(e).__name__}")
        if self._on_command_text is not None:
            self._on_command_text(transcript)
            return
        self._default_command_handler(transcript)

    def _check_vad_gates(self, stats: dict | None = None) -> bool:
        """Check VAD gates. Returns True if ASR should proceed.

        Tolerant rule: if speech_started=true and total duration >= ASR_MIN_AUDIO_MS,
        send to ASR even if speech_ms < VAD_MIN_SPEECH_MS. This prevents
        false rejections where VAD counts speech frames conservatively
        but the recording is clearly valid.
        """
        stats = stats or self._last_capture_stats or {}
        speech_ms = int(stats.get("speech_ms") or 0)
        duration_ms = int(stats.get("duration_ms") or 0)
        speech_started = bool(stats.get("speech_started", False))
        max_rms = float(stats.get("max_rms") or 0.0)
        if speech_started and duration_ms >= ASR_MIN_AUDIO_MS:
            return True
        if speech_ms < VAD_MIN_SPEECH_MS:
            _safe_log(f"[VAD] gate fail reason=speech_too_short speech_ms={speech_ms} min_ms={VAD_MIN_SPEECH_MS} duration_ms={duration_ms}")
            return False
        if max_rms < VAD_MIN_RMS:
            _safe_log(f"[VAD] gate fail reason=rms_too_low rms={max_rms:.4f} min_rms={VAD_MIN_RMS:.4f}")
            return False
        return True

    def _save_empty_audio(self, audio_pcm16_bytes: bytes) -> None:
        try:
            import os
            from pathlib import Path
            artifacts_dir = Path("artifacts")
            artifacts_dir.mkdir(exist_ok=True)
            wav_path = str(artifacts_dir / "last_empty_asr.wav")
            with open(wav_path, "wb") as f:
                import struct
                n = len(audio_pcm16_bytes) // 2
                sample_rate = SAMPLE_RATE
                data_size = len(audio_pcm16_bytes)
                wav_header = struct.pack(
                    "<4sI4s4sIHHIIHH4sI",
                    b"RIFF", 36 + data_size, b"WAVE",
                    b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
                    b"data", data_size
                )
                f.write(wav_header)
                f.write(audio_pcm16_bytes)
            _safe_log(f"[ASR] empty_audio_saved path={wav_path} bytes={len(audio_pcm16_bytes)}")
        except Exception as e:
            _safe_log(f"[ASR] save_empty_audio_failed reason={type(e).__name__}")

    def emit_command(self, audio_pcm16_bytes: bytes, source: str = "voice") -> str:
        """Run ASR on the captured audio and dispatch the transcript."""
        uses_default_asr = self._asr is _default_asr
        if uses_default_asr and not self._check_vad_gates():
            self._save_empty_audio(audio_pcm16_bytes)
            self._post_status("asr_result", source=source, text="")
            return ""
        if uses_default_asr and (not audio_pcm16_bytes or len(audio_pcm16_bytes) < (ASR_MIN_AUDIO_MS / 1000.0) * SAMPLE_RATE * 2):
            _safe_log(f"[ASR] skipped reason=audio_too_short bytes={len(audio_pcm16_bytes or b'')} min_bytes={int(ASR_MIN_AUDIO_MS / 1000.0 * SAMPLE_RATE * 2)}")
            self._save_empty_audio(audio_pcm16_bytes)
            self._post_status("asr_result", source=source, text="")
            return ""
        self._post_status("asr_started", source=source)
        transcript = (self._asr(audio_pcm16_bytes, SAMPLE_RATE) or "").strip()
        self._post_status("asr_result", source=source, text=transcript[:80])
        if not transcript:
            _safe_log("[ASR] provider=groq success chars=0")
            self._save_empty_audio(audio_pcm16_bytes)
            return ""
        # Safe preview only (cap at 60 chars).
        preview = transcript[:60].replace("\n", " ")
        _safe_log(f"[VOICE] received: {preview}")
        _safe_log(f"[ROUTER] received: {preview}")
        self._dispatch_transcript(transcript, source)
        return transcript

    def trigger_wake(self, source: str = "hotword", *, already_arbitrated: bool = False, confidence: float = 1.0, reason: str = "manual") -> bool:
        """Run the internal wake -> VAD -> ASR -> bridge flow.

        Session lifecycle:
          start_session() at entry
          finish_session() on: ASR empty, speech timeout, command error, exception
          Session persists through ASR+command+TTS (finished by bridge on sleep)
        """
        try:
            src = (source or "hotword").strip().lower()
            if src in {"clap", "double-clap", "double clap"}:
                src = "double_clap"
            source = src
        except Exception:
            source = (source or "hotword").strip() or "hotword"
        if not already_arbitrated:
            decision = self._evaluate_wake_candidate(source, True, confidence, self._clock(), reason)
            if not decision.should_wake:
                _safe_log(f"[WAKE] ignored source={source} reason={decision.reason}")
                return False
            source = decision.source

        try:
            from engine.barge_in_manager import interrupt as interrupt_speech
            result = interrupt_speech(source=source, reason="wake_detected")
            if result.interrupted:
                self._post_status("interrupted", source=source)
        except Exception:
            pass

        session_id = start_session(source)
        if self._wake_signal_bus is not None:
            self._wake_signal_bus.emit_wake(
                self._WakeSignal(
                    source=source,
                    state="wake_detected",
                    confidence=confidence,
                    timestamp=self._clock(),
                    reason=reason,
                    session_id=session_id,
                )
            )

        if WAKE_ACTION != "nexi_internal":
            _safe_log(f"[WAKE] unsupported_action={WAKE_ACTION}; using internal wake")
        with self._capture_lock:
            if self._wake_orch is not None:
                self._wake_orch.mark_listening_started()
            if self._wake_signal_bus is not None:
                self._wake_signal_bus.emit_listening_started(source, session_id=session_id)
            try:
                from engine.nexi_wake_controller import wake_nexi
                wake_nexi(source)
            except Exception as e:
                _safe_log(f"[WAKE] internal_wake failed reason={type(e).__name__}")
                if self._wake_orch is not None:
                    self._wake_orch.mark_listening_finished()
                self._post_status("sleeping", source=source)
                finish_session("internal_wake_failed")
                return False
            try:
                _safe_log(f"[VAD] listening_for_command source={source}")
                self.flush_wake_tail()

                # Non-blocking wake confirmation TTS
                if _env_bool("NEXI_WAKE_CONFIRMATION_ENABLED", False):
                    confirm_text = _env("NEXI_WAKE_CONFIRMATION_TEXT", "Awake, sir.")
                    if confirm_text:
                        try:
                            _safe_log(f"[WAKE_CONFIRM] speak text={confirm_text}")
                            from engine.command import speak
                            speak(confirm_text)
                        except Exception as ce:
                            _safe_log(f"[WAKE_CONFIRM] speak_failed reason={type(ce).__name__}")

                if POST_WAKE_DELAY_MS > 0:
                    delay_sec = POST_WAKE_DELAY_MS / 1000.0
                    _safe_log(f"[VAD] post_wake_delay_ms={POST_WAKE_DELAY_MS} source={source}")
                    deadline = time.monotonic() + delay_sec
                    while time.monotonic() < deadline:
                        try:
                            self._frame_queue.get(timeout=0.05)
                        except queue.Empty:
                            pass
                    self._preroll.clear()

                def _next_frame() -> Optional[bytes]:
                    try:
                        return self._frame_queue.get(timeout=0.2)
                    except queue.Empty:
                        return None

                audio = self.capture_command(_next_frame, source=source)
                stats = self._last_capture_stats or {}
                if not stats.get("speech_started", False) or len(audio) < (ASR_MIN_AUDIO_MS / 1000.0) * SAMPLE_RATE * 2:
                    _safe_log("[COMMAND_CAPTURE] no_speech_timeout reached")
                    if self._wake_orch is not None:
                        self._wake_orch.mark_listening_finished()
                    self._post_status("sleeping", source=source)
                    finish_session("no_speech_timeout")
                    return False
                try:
                    transcript = self.emit_command(audio, source=source)
                    self._last_wake_at = self._clock()
                    self.flush_wake_tail()
                    if not transcript:
                        self._post_status("sleeping", source=source)
                        finish_session("asr_empty")
                        if self._wake_orch is not None:
                            self._wake_orch.mark_listening_finished()
                        _safe_log("[COMMAND_CAPTURE] asr_empty — session finished")
                        return False
                    # With an async command queue, the runtime bridge owns the
                    # rest of the session lifecycle (recognising -> thinking ->
                    # speaking) and resumes the detectors only after TTS finishes.
                    # Finishing the session here would re-open the mic mid-response
                    # and let Nexi re-wake on its own speech.
                    if self._command_queue is not None and get_session_manager().is_active():
                        _safe_log("[COMMAND_CAPTURE] command dispatched — session owned by bridge")
                        return True
                    self._post_status("sleeping", source=source)
                    finish_session("command_complete")
                    _safe_log("[COMMAND_CAPTURE] command_complete — session finished")
                    return True
                except Exception as e:
                    _safe_log(f"[VOICE] emit_command failed reason={type(e).__name__}")
                    self._post_status("sleeping", source=source)
                    finish_session("emit_command_failed")
                    return False
            except Exception as e:
                _safe_log(f"[VOICE] capture_command failed reason={type(e).__name__}")
                self._post_status("sleeping", source=source)
                finish_session("capture_command_failed")
                return False
            finally:
                if self._wake_orch is not None:
                    self._wake_orch.mark_listening_finished()

    def flush_wake_tail(self) -> int:
        """Drain wake-phrase tail frames before command capture starts."""
        flush_frames = max(0, int((WAKE_FLUSH_AUDIO_MS / 1000.0) * SAMPLE_RATE / FRAME_SAMPLES))
        drained = 0
        for _ in range(flush_frames):
            try:
                self._frame_queue.get(timeout=0.05)
                drained += 1
            except queue.Empty:
                break
        self._preroll.clear()
        return drained

    # ---- live runtime ----

    def start(self) -> None:
        self._last_start_error = ""
        clap_enabled = self.is_clap_enabled()
        if not OWW_ENABLED:
            self._last_start_error = "openwakeword_disabled"
            _safe_log("[WAKE] backend=openwakeword enabled=False")
            _safe_log("[HOTWORD] enabled=false")
            if not clap_enabled:
                return
        if self.is_running:
            return

        # Lazy-build scorer
        if OWW_ENABLED and self._wake_scorer is None:
            try:
                self._wake_scorer = OpenWakeWordScorer(
                    model_path=OWW_MODEL_PATH, pretrained=OWW_PRETRAINED
                )
            except ImportError as e:
                self._last_start_error = "scorer_import_error"
                _safe_log(f"[WAKE] openwakeword unavailable reason={e}")
                self._wake_scorer = None
            except Exception as e:
                self._last_start_error = f"scorer_{type(e).__name__}"
                _safe_log(f"[WAKE] model_load_failed reason={type(e).__name__}")
                self._wake_scorer = None

        if self._wake_scorer is None and not clap_enabled:
            if not self._last_start_error:
                self._last_start_error = "scorer_missing"
            _safe_log(f"[WAKE] scorer_loaded=no reason={self._last_start_error}")
            return

        if self._wake_scorer is not None:
            model_safe = os.path.basename(OWW_MODEL_PATH) if OWW_MODEL_PATH else OWW_PRETRAINED
            _safe_log("[HOTWORD] enabled=true")
            _safe_log(f"[HOTWORD] model_path={model_safe}")
            _safe_log(f"[HOTWORD] sample_rate={SAMPLE_RATE}")
            _safe_log(f"[HOTWORD] frame_ms={int((FRAME_SAMPLES / SAMPLE_RATE) * 1000)}")
            _safe_log(f"[HOTWORD] threshold={OWW_THRESHOLD}")
        else:
            _safe_log(f"[HOTWORD] enabled=false reason={self._last_start_error or 'no_scorer'}")

        # Lazy-build VAD
        if self._vad is None:
            self._vad = build_vad()

        # Open mic
        try:
            self._open_stream()
        except Exception as e:
            self._last_start_error = f"mic_{type(e).__name__}"
            _safe_log(f"[WAKE] mic_unavailable reason={type(e).__name__}")
            return

        _safe_log(f"[WAKE] backend=openwakeword enabled=True")
        _safe_log(f"[CLAP] enabled={str(self.is_clap_enabled()).lower()}")
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None

    # ---- audio stream ----

    def _open_stream(self) -> None:
        import sounddevice as sd  # lazy
        import numpy as np

        # Resolve input device. AUDIO_INPUT_DEVICE="auto" => smart selection
        # (enumerate, test-open at this rate, prefer a headset mic); a numeric
        # index or name pins a specific device; empty/"default" uses the OS one.
        device = None
        spec = (AUDIO_INPUT_DEVICE or "").strip()
        if spec and spec.lower() not in {"auto", "default"}:
            device = int(spec) if spec.isdigit() else spec
        elif spec.lower() == "auto":
            try:
                from engine.mic_selector import select_best_mic
                best, ranked = select_best_mic(SAMPLE_RATE, CHANNELS)
                if best is not None:
                    device = best["index"]
                    _safe_log(f"[MIC] auto_selected device={best['name']} index={device} score={best['score']}")
                    runner = next((r for r in ranked if r["openable"] and r["index"] != device), None)
                    if runner:
                        _safe_log(f"[MIC] fallback_candidate device={runner['name']} index={runner['index']}")
                else:
                    _safe_log("[MIC] auto_select found no openable device — using OS default")
            except Exception as e:
                _safe_log(f"[MIC] auto_select_failed reason={type(e).__name__} — using OS default")

        try:
            dev_info = sd.query_devices(device, "input") if device is not None else sd.query_devices(kind="input")
            dev_name = dev_info.get("name", device or "default")
        except Exception:
            dev_name = str(device if device is not None else "default")
        _safe_log(f"[WAKE] audio stream starting device={dev_name} index={device if device is not None else 'default'} rate={SAMPLE_RATE} frame={FRAME_SAMPLES}")

        def _callback(indata, frames, time_info, status):
            # Audio thread: do NOT block. Push int16 bytes to the queue.
            try:
                pcm = (indata[:, 0] * 32767.0).clip(-32768, 32767).astype(np.int16).tobytes()
                self._frame_queue.put_nowait(pcm)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                    self._frame_queue.put_nowait(pcm)
                except Exception:
                    pass
            except Exception:
                pass

        kwargs = dict(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            blocksize=FRAME_SAMPLES,
            dtype="float32",
            callback=_callback,
        )
        if device is not None:
            kwargs["device"] = device

        try:
            self._stream = sd.InputStream(**kwargs)
            self._stream.start()
        except Exception as e:
            _safe_log(f"[WAKE] device open failed index={device} reason={type(e).__name__} — falling back to OS default")
            kwargs.pop("device", None)
            device = None
            dev_name = "default"
            self._stream = sd.InputStream(**kwargs)
            self._stream.start()
        _safe_log(f"[WAKE] audio stream started device={dev_name}/{device if device is not None else 'default'}")

    # ---- worker loop ----

    def _worker_loop(self) -> None:
        _debug_interval = 1.0  # seconds between debug prints
        _last_debug = 0.0
        _frame_count = 0
        while not self._stop_event.is_set():
            try:
                frame = self._frame_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            _frame_count += 1
            if WAKE_DEBUG and not self._audio_received_logged:
                _safe_log("[HOTWORD] audio_chunk_received=true")
                self._audio_received_logged = True
            try:
                result = self.process_frame(frame)
            except Exception as e:
                _safe_log(f"[WAKE] process_frame failed reason={type(e).__name__}")
                continue

            # Periodic debug line so user sees the pipeline is alive.
            if WAKE_DEBUG:
                now_dbg = time.time()
                if now_dbg - _last_debug >= _debug_interval:
                    _rms, _peak = _calc_rms_peak(frame)
                    scorer_name = getattr(self._wake_scorer, "model_name", getattr(self._wake_scorer, "name", "none"))
                    clap_state = f"enabled={str(self.is_clap_enabled()).lower()}"
                    _safe_log(f"[AUDIO] frames={_frame_count} rms={_rms:.4f} peak={_peak:.4f} queue={self._frame_queue.qsize()}")
                    _safe_log(f"[WAKE] score model={scorer_name} score={result.get('score', 0):.4f} threshold={OWW_THRESHOLD} hits={self._consecutive_hits}/{OWW_CONSECUTIVE}")
                    if hasattr(self._wake_scorer, "get_debug_snapshot"):
                        snap = self._wake_scorer.get_debug_snapshot()
                        if snap.get("prediction_keys"):
                            _safe_log(f"[HOTWORD] prediction_keys={snap.get('prediction_keys')} selected_key={snap.get('selected_key')}")
                    _safe_log(f"[HOTWORD] score={result.get('score', 0):.4f}")
                    _safe_log(f"[HOTWORD] threshold={OWW_THRESHOLD}")
                    _safe_log(f"[HOTWORD] detected={str(bool(result.get('wake') and result.get('source') == 'hotword')).lower()}")
                    _safe_log(f"[CLAP] rms={_rms:.4f} peak={_peak:.4f} state={clap_state}")
                    _last_debug = now_dbg

            if get_session_manager().check_timeout():
                pass
            if not result.get("wake"):
                continue

            source = result.get("source", "hotword")
            if source == "double_clap":
                _safe_log("[CLAP] double_clap_detected=true")
            else:
                _safe_log(f"[WAKE] detected source=hotword model={getattr(self._wake_scorer, 'model_name', 'unknown')}")
                _safe_log("[HOTWORD] detected=true")
            emitted = self.trigger_wake(source, already_arbitrated=True, confidence=float(result.get("score") or 1.0), reason=str(result.get("reason") or "detected"))
            _safe_log(f"[WAKE] source={source} emitted={str(bool(emitted)).lower()}")
            # Drain mic audio that piled up while the (blocking) wake turn ran,
            # so detection resumes on FRESH input immediately instead of chewing
            # through a stale backlog — keeps the hotword responsive right after
            # a turn finishes / it goes back to sleep.
            drained = self.flush_wake_tail()
            if drained:
                _safe_log(f"[WAKE] post_turn_flush drained={drained} frames — detection re-armed")


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

_global_pipeline: Optional[AudioWakePipeline] = None
_global_hotkey_listener = None
_last_start_error = ""


def start_audio_wake_pipeline(on_command_text: Optional[Callable[[str], None]] = None, command_queue=None) -> None:
    global _global_pipeline, _global_hotkey_listener, _last_start_error
    if _global_pipeline is not None and _global_pipeline.is_running:
        return
    _global_pipeline = AudioWakePipeline(on_command_text=on_command_text, command_queue=command_queue)
    _global_pipeline.start()
    _last_start_error = _global_pipeline.last_start_error
    if _global_pipeline.is_running:
        try:
            from engine.hotkey_wake import start_hotkey_listener
            _global_hotkey_listener = start_hotkey_listener(callback=trigger_audio_wake)
        except Exception as e:
            _safe_log(f"[HOTKEY] start_failed reason={type(e).__name__}")


def stop_audio_wake_pipeline() -> None:
    global _global_pipeline, _global_hotkey_listener
    if _global_hotkey_listener is not None:
        try:
            from engine.hotkey_wake import stop_hotkey_listener
            stop_hotkey_listener(_global_hotkey_listener)
        except Exception:
            pass
        _global_hotkey_listener = None
    if _global_pipeline is not None:
        _global_pipeline.stop()
    _global_pipeline = None


def trigger_audio_wake(source: str = "hotkey") -> bool:
    if _global_pipeline is None or not _global_pipeline.is_running:
        _safe_log("[HOTKEY] wake_ignored reason=pipeline_not_running")
        return False
    return _global_pipeline.trigger_wake(source)


def is_pipeline_running() -> bool:
    return _global_pipeline is not None and _global_pipeline.is_running


def get_last_start_error() -> str:
    if _global_pipeline is not None and _global_pipeline.last_start_error:
        return _global_pipeline.last_start_error
    return _last_start_error
