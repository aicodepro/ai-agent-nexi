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

import math
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
# Anti-false-wake defaults for the custom hey_nexi model. 0.25/1 fired on a
# single noisy frame ("wake from nowhere" in conversation). 0.35 matches the
# recommended starting point for a custom model, and requiring 2 consecutive
# hits is a debounce a real "hey nexi" easily clears while single-frame noise
# spikes do not. Tune via .env: lower if it misses your wake word, raise if it
# still self-triggers. Watch the per-frame `[HOTWORD] score=... hits=...` logs.
OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)
OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2)
WAKE_COOLDOWN_SECONDS = _env_float("WAKE_COOLDOWN_SECONDS", _env_int("NEXI_WAKE_COOLDOWN_MS", _env_int("OPENWAKEWORD_COOLDOWN_MS", 1500)) / 1000.0)
HOTWORD_MIN_RMS = _env_float("NEXI_HOTWORD_MIN_RMS", 0.003)
# Wake noise-rejection: require Silero-detected VOICE (not just energy) to wake,
# so office noise that trips the energy gate still cannot wake NEXI. The wake
# scorer effectively fires on any energy, so this voice gate is the real filter.
WAKE_REQUIRE_VOICE = (os.getenv("NEXI_WAKE_REQUIRE_VOICE", "0") or "0").strip().lower() not in {"0", "false", "no", "off"}
# Wake energy bar: require the hotword frame to have enough energy. 0.015
# catches whisper-level speech close to the mic while rejecting fan/ambient.
# Raise (e.g. 0.03) in very noisy rooms to avoid false energy wakes.
WAKE_MIN_RMS = _env_float("NEXI_WAKE_MIN_RMS", 0.015)
_WAKE_RMS_FLOOR = max(HOTWORD_MIN_RMS, WAKE_MIN_RMS)
HOTWORD_RISING_EDGE_DELTA = _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.02)
AUDIO_INPUT_DEVICE = _env("AUDIO_INPUT_DEVICE", "auto")
WAKE_DEBUG = _env_bool("WAKE_DEBUG", False) or _env_bool("NEXI_WAKE_DEBUG", False) or _env_bool("OPENWAKEWORD_DEBUG", False)

# Adaptive noise calibration
# The floor multiplier is intentionally conservative (1.5x) to keep quiet/whispered
# speech detectable. The ceiling caps the floor so it never blocks the quietest
# intentional utterance (RMS ~0.005-0.008). Real ambient noise calibration happens
# in calibrate_noise_floor().
NOISE_CALIBRATION_SECONDS = _env_float("NEXI_NOISE_CALIBRATION_SECONDS", 2.0)
NOISE_CALIBRATION_MULTIPLIER = _env_float("NEXI_NOISE_CALIBRATION_MULTIPLIER", 1.5)
NOISE_CALIBRATION_MIN_RMS = _env_float("NEXI_NOISE_CALIBRATION_MIN_RMS", 0.003)
NOISE_CALIBRATION_MAX_RMS = _env_float("NEXI_NOISE_CALIBRATION_MAX_RMS", 0.025)

VAD_BACKEND = _env("VAD_BACKEND", "silero")
VAD_MIN_SPEECH_MS = _env_int("VAD_MIN_SPEECH_MS", _env_int("NEXI_COMMAND_MIN_SPEECH_MS", 400))
VAD_SILENCE_END_MS = _env_int("VAD_SILENCE_END_MS", _env_int("ASR_SILENCE_TIMEOUT_MS", _env_int("NEXI_COMMAND_END_SILENCE_MS", 2200)))
COMMAND_LISTEN_TIMEOUT_SECONDS = _env_float(
    "COMMAND_LISTEN_TIMEOUT_SECONDS",
    _env_float("ASR_MAX_RECORD_SECONDS", _env_float("VAD_MAX_COMMAND_SECONDS", _env_float("NEXI_COMMAND_MAX_SPEECH_MS", 30000) / 1000.0)),
)
NO_SPEECH_TIMEOUT_SECONDS = _env_float("NEXI_COMMAND_NO_SPEECH_TIMEOUT_MS", 15000) / 1000.0
_BARGE_IN_TRANSACTION_TIMEOUT_SECONDS = max(
    1.0,
    _env_float("NEXI_BARGE_IN_TRANSACTION_TIMEOUT_SECONDS", 15.0),
)
# The soft deadline above is renewed while TTS is still winding down, because a
# transaction that expires mid-stop leaves NOTHING blocking the next candidate:
# _pending_barge_in becomes None, the "barge_in_pending" guard stops firing, and
# one spoken wake word opens a SECOND interrupt. Live trace:
#   [BARGE_IN] transaction_expired -> [BARGE_IN] hotword_during_speaking (again)
# The hard deadline is the absolute cap so a stuck TTS producer cannot pin the
# transaction open forever.
_BARGE_IN_HARD_TIMEOUT_SECONDS = max(
    _BARGE_IN_TRANSACTION_TIMEOUT_SECONDS,
    _env_float("NEXI_BARGE_IN_HARD_TIMEOUT_SECONDS", 45.0),
)
# After a transaction closes (captured OR expired), ignore wake candidates
# briefly. One utterance of "hey nexi" spans many frames; without this the tail
# of the SAME utterance immediately opens the next transaction.
_BARGE_IN_REFRACTORY_SECONDS = max(
    0.0,
    _env_float("NEXI_BARGE_IN_REFRACTORY_SECONDS", 2.0),
)
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
    """Audio-process truth for active TTS, updated through the control queue."""
    try:
        return bool(get_session_manager().is_tts_active())
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
        control_queue=None,
    ):
        self._on_command_text = on_command_text
        self._command_queue = command_queue
        self._control_queue = control_queue
        self._asr = asr or _default_asr
        self._clock = clock or time.time
        self._wake_scorer = wake_scorer  # built lazily in start() if None
        self._vad = vad  # built lazily in start() if None
        self._wake_vad = None  # separate Silero VAD for the wake voice-gate (lazy)

        self._enable_clap = enable_clap
        self._frame_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=256)
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._stream = None
        self._last_start_error = ""
        self._capture_lock = threading.Lock()
        self._audio_received_logged = False
        self._last_frame_time = 0.0
        self._mic_disconnect_logged = False
        self._mic_reconnect_attempts = 0
        self._last_mic_retry = 0.0
        self._last_capture_stats: dict = {}
        self._pending_session_finishes: dict[str, str] = {}
        self._pending_barge_in: dict | None = None
        self._barge_in_refractory_until = 0.0
        self._pending_tts_watchdog: dict | None = None

        # Per-frame wake state
        self._consecutive_hits = 0
        self._last_wake_at = 0.0
        self._prev_hotword_score = 0.0
        # Rolling window of recent frame RMS (~1.2s). openWakeWord's score peaks with
        # a buffer delay — often on a near-silent frame AFTER the phrase — so the wake
        # gate must ask "was there speech recently?", not "is THIS frame loud?".
        self._recent_rms = deque(maxlen=_env_int("NEXI_WAKE_RMS_WINDOW_FRAMES", 15))

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

    def _maybe_capture_pending_barge_in(self) -> bool:
        pending = self._pending_barge_in
        if not pending or not all(
            pending.get(flag) for flag in ("acked", "terminal", "cooldown")
        ):
            return False
        session_id = str(pending.get("session_id") or "")
        self._pending_session_finishes.pop(session_id, None)
        self._pending_barge_in = None
        self._barge_in_refractory_until = time.time() + _BARGE_IN_REFRACTORY_SECONDS
        return bool(self._capture_barge_in(pending))

    def _expire_pending_barge_in(self) -> bool:
        pending = self._pending_barge_in
        if not pending:
            return False
        now = time.time()
        if now < float(pending.get("deadline") or 0.0):
            return False
        manager = get_session_manager()
        # TTS has not acknowledged the stop yet. Expiring here would clear the
        # only thing rejecting further candidates, so renew instead - bounded by
        # the hard deadline.
        hard_deadline = float(pending.get("hard_deadline") or 0.0)
        if now < hard_deadline and (manager.is_tts_active() or manager.is_tts_cooldown_active()):
            pending["deadline"] = now + _BARGE_IN_TRANSACTION_TIMEOUT_SECONDS
            if not pending.get("renew_logged"):
                pending["renew_logged"] = True
                _safe_log("[BARGE_IN] transaction_renewed reason=tts_not_acknowledged")
            return False
        session_id = str(pending.get("session_id") or "")
        self._pending_barge_in = None
        # A closed transaction must still suppress the tail of the utterance
        # that opened it, or the next frame starts transaction number two.
        self._barge_in_refractory_until = now + _BARGE_IN_REFRACTORY_SECONDS
        _safe_log(f"[BARGE_IN] transaction_expired id={session_id}")
        if session_id and manager.is_current(session_id):
            if manager.is_tts_active() or manager.is_tts_cooldown_active():
                self._pending_session_finishes[session_id] = "barge_in_transaction_timeout"
            else:
                finish_session("barge_in_transaction_timeout")
        return True

    def _dispatch_tts_watchdog_request(self) -> bool:
        if self._pending_tts_watchdog is not None:
            return False
        manager = get_session_manager()
        request = manager.take_tts_watchdog_request()
        if request is None:
            return False
        if self._command_queue is None:
            manager.retry_tts_watchdog_request(str(request.get("request_id") or ""))
            return False
        try:
            self._command_queue.put_nowait(dict(request))
        except Exception:
            manager.retry_tts_watchdog_request(str(request.get("request_id") or ""))
            return False
        self._pending_tts_watchdog = {
            **request,
            "acked": False,
            "terminal": False,
            "cooldown": False,
        }
        return True

    def _maybe_complete_tts_watchdog(self) -> bool:
        pending = self._pending_tts_watchdog
        if not pending or not all(
            pending.get(flag) for flag in ("acked", "terminal", "cooldown")
        ):
            return False
        manager = get_session_manager()
        request_id = str(pending.get("request_id") or "")
        if not manager.complete_tts_watchdog(request_id):
            return False
        self._pending_tts_watchdog = None
        if pending.get("scope") == "voice":
            session_id = str(pending.get("session_id") or "")
            if session_id and manager.is_current(session_id):
                self._pending_session_finishes.pop(session_id, None)
                finish_session(str(pending.get("reason") or "tts_watchdog_stopped"))
        return True

    def _drain_control_events(self) -> int:
        if self._control_queue is None:
            return 0
        handled = 0
        while True:
            try:
                event = self._control_queue.get_nowait()
            except queue.Empty:
                break
            except Exception:
                break
            handled += 1
            if not isinstance(event, dict):
                continue
            session_id = str(event.get("session_id") or "")
            manager = get_session_manager()
            event_type = str(event.get("type") or "")
            if event_type == "turn_progress":
                if not manager.renew_turn_progress(session_id):
                    _safe_log(f"[SESSION] stale_progress_ignored id={session_id}")
                continue
            if event_type == "barge_in_ack":
                pending = self._pending_barge_in
                try:
                    session_epoch = float(event.get("session_epoch") or 0.0)
                except (TypeError, ValueError):
                    session_epoch = 0.0
                if (
                    pending
                    and session_id == pending.get("session_id")
                    and session_epoch == float(pending.get("session_epoch") or 0.0)
                    and str(event.get("request_id") or "") == pending.get("request_id")
                ):
                    if bool(event.get("accepted", False)):
                        continuation_token = str(event.get("continuation_token") or "")
                        if continuation_token:
                            pending["continuation_token"] = continuation_token
                            pending["acked"] = True
                            self._maybe_capture_pending_barge_in()
                    else:
                        self._pending_barge_in = None
                continue
            if event_type == "tts_watchdog_ack":
                pending = self._pending_tts_watchdog
                if pending and all(
                    (
                        str(event.get("request_id") or "") == str(pending.get("request_id") or ""),
                        session_id == str(pending.get("session_id") or ""),
                        float(event.get("session_epoch") or 0.0) == float(pending.get("session_epoch") or 0.0),
                        str(event.get("lease_id") or "") == str(pending.get("lease_id") or ""),
                        str(event.get("producer_id") or "") == str(pending.get("producer_id") or ""),
                    )
                ):
                    pending["acked"] = bool(event.get("stopped", False))
                    self._maybe_complete_tts_watchdog()
                continue
            if event_type in {"global_tts_started", "global_tts_heartbeat", "global_tts_finished", "global_tts_interrupted", "global_cooldown_complete"}:
                lease_id = str(event.get("lease_id") or "")
                try:
                    sequence = int(event.get("sequence") or 0)
                except (TypeError, ValueError):
                    sequence = 0
                if not manager.apply_global_tts_lifecycle(lease_id, event_type, sequence):
                    _safe_log(f"[TTS] stale_global_lifecycle_ignored lease={lease_id} type={event_type} sequence={sequence}")
                else:
                    pending_watchdog = self._pending_tts_watchdog
                    if (
                        pending_watchdog
                        and pending_watchdog.get("scope") == "global"
                        and pending_watchdog.get("lease_id") == lease_id
                    ):
                        if event_type == "global_tts_interrupted":
                            pending_watchdog["terminal"] = True
                        elif event_type == "global_cooldown_complete":
                            pending_watchdog["cooldown"] = True
                        self._maybe_complete_tts_watchdog()
                continue
            if event_type in {"tts_started", "tts_heartbeat", "tts_finished", "tts_interrupted", "cooldown_complete"}:
                if not session_id or not manager.is_current(session_id):
                    if session_id:
                        _safe_log(f"[SESSION] stale_control_ignored id={session_id}")
                    continue
                try:
                    sequence = int(event.get("sequence") or 0)
                except (TypeError, ValueError):
                    sequence = 0
                producer_id = str(event.get("producer_id") or "")
                if not manager.apply_tts_lifecycle(session_id, event_type, sequence, producer_id):
                    _safe_log(f"[SESSION] stale_lifecycle_ignored id={session_id} type={event_type} sequence={sequence}")
                    continue
                _safe_log(f"[SESSION] lifecycle_applied id={session_id} type={event_type} sequence={sequence}")
                if event_type == "tts_interrupted" and self._pending_barge_in:
                    if self._pending_barge_in.get("session_id") == session_id:
                        self._pending_barge_in["terminal"] = True
                        self._maybe_capture_pending_barge_in()
                if event_type == "tts_interrupted" and self._pending_tts_watchdog:
                    pending_watchdog = self._pending_tts_watchdog
                    if (
                        pending_watchdog.get("scope") == "voice"
                        and pending_watchdog.get("session_id") == session_id
                        and str(pending_watchdog.get("producer_id") or "") == producer_id
                    ):
                        pending_watchdog["terminal"] = True
                        self._maybe_complete_tts_watchdog()
                if event_type == "cooldown_complete":
                    pending_watchdog = self._pending_tts_watchdog
                    if (
                        pending_watchdog
                        and pending_watchdog.get("scope") == "voice"
                        and pending_watchdog.get("session_id") == session_id
                        and str(pending_watchdog.get("producer_id") or "") == producer_id
                    ):
                        pending_watchdog["cooldown"] = True
                        self._maybe_complete_tts_watchdog()
                    pending = self._pending_barge_in
                    if pending and pending.get("session_id") == session_id:
                        pending["cooldown"] = True
                        self._maybe_capture_pending_barge_in()
                    else:
                        reason = self._pending_session_finishes.pop(session_id, "")
                        if reason:
                            finish_session(reason)
                continue
            if event_type == "capture_followup":
                if session_id and manager.is_current(session_id):
                    self._capture_followup(event)
                elif session_id:
                    _safe_log(f"[SESSION] stale_control_ignored id={session_id}")
                continue
            if event_type != "finish_session":
                continue
            if session_id and manager.is_current(session_id):
                reason = str(event.get("reason") or "complete")
                if bool(event.get("force", False)):
                    self._pending_session_finishes.pop(session_id, None)
                    finish_session(reason)
                elif manager.is_tts_active() or manager.is_tts_cooldown_active():
                    self._pending_session_finishes[session_id] = reason
                    _safe_log(f"[SESSION] finish_deferred id={session_id} reason=tts_lifecycle")
                else:
                    finish_session(reason)
            elif session_id:
                _safe_log(f"[SESSION] stale_control_ignored id={session_id}")
        self._expire_pending_barge_in()
        self._dispatch_tts_watchdog_request()
        return handled

    def _capture_followup(self, event: dict) -> bool:
        session_id = str(event.get("session_id") or "")
        source = str(event.get("source") or "voice").strip() or "voice"
        manager = get_session_manager()
        if not session_id or not manager.is_current(session_id):
            return False

        not_before = float(event.get("not_before") or 0.0)
        while time.time() < not_before:
            remaining = max(0.0, not_before - time.time())
            try:
                self._frame_queue.get(timeout=min(0.05, remaining))
            except queue.Empty:
                pass

        try:
            self.flush_wake_tail()
            manager.set_state("listening")
            self._post_status("listening_started", source=source)
            _safe_log(f"[LISTEN] followup_capture_started source={source}")

            def _next_frame() -> Optional[bytes]:
                try:
                    return self._frame_queue.get(timeout=0.2)
                except queue.Empty:
                    return None

            audio = self.capture_command(_next_frame, source=source, followup=True)
            stats = self._last_capture_stats or {}
            if not stats.get("speech_started", False) or len(audio) < (ASR_MIN_AUDIO_MS / 1000.0) * SAMPLE_RATE * 2:
                self._post_status("sleeping", source=source)
                finish_session("followup_no_speech_timeout")
                return False
            transcript = self.emit_command(audio, source=source)
            self.flush_wake_tail()
            if not transcript:
                self._post_status("sleeping", source=source)
                finish_session("followup_asr_empty")
                return False
            manager.set_state("thinking")
            return True
        except Exception as exc:
            _safe_log(f"[LISTEN] followup_capture_failed reason={type(exc).__name__}")
            self._post_status("sleeping", source=source)
            finish_session("followup_capture_failed")
            return False

    def _capture_barge_in(self, pending: dict) -> bool:
        return self._capture_followup({
            "type": "capture_followup",
            "session_id": str(pending.get("session_id") or ""),
            "source": str(pending.get("source") or "hotword"),
            "reason": "barge_in",
            "not_before": 0.0,
        })

    # ---- pure per-frame logic (testable) ----

    def _wake_frame_is_voice(self, frame_int16: bytes) -> bool:
        """Silero voice-gate for waking. True only for voiced speech, so ambient
        office energy (keyboard/door/HVAC/fan) cannot wake NEXI even though the
        wake scorer fires on it. Fails OPEN (returns True) if a VAD is unavailable
        so we never silently stop responding."""
        if self._wake_vad is None:
            try:
                self._wake_vad = build_vad()
            except Exception:
                self._wake_vad = False  # sentinel: unavailable, don't retry
        if not self._wake_vad:
            return True
        try:
            return bool(self._wake_vad.is_speech(frame_int16))
        except Exception:
            return True

    def process_frame(self, frame_int16: bytes) -> dict:
        """Run one frame through the wake detectors.

        Returns a dict describing what happened. Used both in tests and
        in the live worker loop.
        """
        now = self._clock()
        result = {"wake": False, "source": None, "score": 0.0, "cooldown": False, "reason": "none"}

        # --- Barge-in: a wake word spoken WHILE Nexi is talking interrupts
        # the TTS instead of being captured as a command.
        #
        # This MUST precede BOTH the global-TTS and detectors-paused gates.
        # Every one of them is true at exactly the moment Nexi is speaking, so
        # any of them checked first makes barge-in unreachable - the frame
        # returns with score 0.0 and the wake scorer never runs. That left the
        # user unable to interrupt a long answer at all: barge-in only fired in
        # the narrow race before the global TTS lease was applied.
        if _is_speaking():
            if self._pending_barge_in is not None:
                return {"wake": False, "source": None, "reason": "barge_in_pending", "score": 0.0}
            if time.time() < self._barge_in_refractory_until:
                # A transaction just closed. The tail of the same utterance must
                # not open another one.
                return {"wake": False, "source": None, "reason": "barge_in_refractory", "score": 0.0}
            score = self._wake_scorer.score(frame_int16) if self._wake_scorer is not None else 0.0
            if score >= OWW_THRESHOLD:
                self._consecutive_hits = 0
                self._prev_hotword_score = 0.0
                _safe_log(f"[BARGE_IN] hotword_during_speaking score={float(score):.3f}")
                try:
                    from engine.runtime_bridge import post_barge_in_request
                    manager = get_session_manager()
                    session_id = str(manager.get_session_id() or "")
                    session_epoch = manager.get_session_epoch()
                    request_id = post_barge_in_request(
                        self._command_queue,
                        session_id,
                        source="hotword",
                        session_epoch=session_epoch,
                    )
                    if not request_id:
                        raise RuntimeError("barge_in_request_enqueue_failed")
                    self._pending_barge_in = {
                        "session_id": session_id,
                        "session_epoch": session_epoch,
                        "request_id": request_id,
                        "source": "hotword",
                        "continuation_token": "",
                        "acked": False,
                        "terminal": False,
                        "cooldown": False,
                        "created_at": time.time(),
                        "deadline": time.time() + _BARGE_IN_TRANSACTION_TIMEOUT_SECONDS,
                        "hard_deadline": time.time() + _BARGE_IN_HARD_TIMEOUT_SECONDS,
                    }
                except Exception as e:
                    _safe_log(f"[BARGE_IN] request_failed reason={type(e).__name__}")
                    return {"wake": False, "source": None, "reason": "barge_in_request_failed", "score": float(score)}
                return {"wake": False, "source": "hotword", "reason": "barge_in_requested", "score": float(score)}
            return {"wake": False, "source": None, "reason": "speaking", "score": float(score)}

        # Not speaking, but audio is still owned by a TTS lease (another
        # session/process): suppress capture so Nexi never hears itself.
        if get_session_manager().is_global_tts_active():
            result["reason"] = "global_tts_active"
            return result

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
                self._recent_rms.append(rms)
                recent_max = max(self._recent_rms) if self._recent_rms else rms
                # Gate on RECENT speech, not this exact frame. The score for "hey nexi"
                # commonly peaks 1-2 frames AFTER the phrase (openWakeWord buffers ~1s
                # internally), and that peak frame is often near-silent — the old
                # instantaneous `rms < floor` check rejected exactly the frame that
                # fires, which is why normal speech was missed and only shouting worked.
                if recent_max < _WAKE_RMS_FLOOR:
                    result["reason"] = f"low_rms_{rms:.5f}"
                    self._consecutive_hits = 0
                    self._prev_hotword_score = score
                    score = 0.0
                elif WAKE_REQUIRE_VOICE and not self._wake_frame_is_voice(frame_int16):
                    # energy is present but it is NOT voiced speech (office noise) -> don't wake
                    result["reason"] = f"not_speech_rms_{rms:.5f}"
                    self._consecutive_hits = 0
                    self._prev_hotword_score = score
                    score = 0.0
                elif score >= OWW_THRESHOLD:
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

    def capture_command(
        self,
        frame_source: Callable[[], Optional[bytes]],
        source: str = "voice",
        followup: bool | None = None,
    ) -> bytes:
        """Capture frames after a wake event until VAD silence or max duration.

        `frame_source()` returns the next frame or None when no more frames
        are available. Pre-roll frames are prepended automatically so the
        first word isn't clipped.
        """
        vad = self._vad or build_vad()
        if self._vad is None:
            self._vad = vad

        frame_ms = max(1.0, (FRAME_SAMPLES / SAMPLE_RATE) * 1000.0)
        followup_capture = bool(followup)
        if followup is None:
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
        speech_start_index: int | None = None
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
                    speech_start_index = len(captured) - 1
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

        # Drop the dead air recorded BEFORE the user actually started speaking.
        # We keep VAD_PREROLL_MS of lead-in so the first phoneme is never clipped.
        # This matters for latency, not disk: the ASR round-trip is dominated by the
        # UPLOAD, and we were shipping every second of silence while the user thought
        # about what to say (measured: 11.6s recorded / 0.96s speech = 371KB posted).
        if speech_started and speech_start_index is not None:
            lead_frames = self._preroll.maxlen or 0
            keep_from = max(0, speech_start_index - lead_frames)
            # NEVER trim below what the ASR needs. The caller rejects any clip shorter
            # than ASR_MIN_AUDIO_MS as "no_speech_timeout", so an over-eager trim made
            # short utterances ("what's up?") die with listening -> thinking -> sleep.
            # Keep extra lead-in rather than produce a too-short clip.
            # ceil, not int(): int(1800/80)=22 frames = 1760ms, which is still UNDER
            # the 1800ms minimum and gets discarded as no_speech_timeout.
            min_frames = max(1, math.ceil(ASR_MIN_AUDIO_MS / frame_ms))
            if len(captured) - keep_from < min_frames:
                keep_from = max(0, len(captured) - min_frames)
            if keep_from > 0:
                trimmed_ms = int(keep_from * frame_ms)
                captured = captured[keep_from:]
                _safe_log(f"[VAD] trimmed_leading_silence_ms={trimmed_ms} kept_ms={int(len(captured) * frame_ms)}")

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
        # Speech that never started cannot have ended. Emitting "speech_ended"
        # from LISTENING produced `transition_failed reason=no_valid_transition`
        # and drove the UI to "Recognising speech..." when there was no speech -
        # actively misleading for a screen-reader user.
        self._post_status("speech_ended" if speech_started else "no_speech_timeout", source=source)
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

    # ---- adaptive noise calibration ----

    def calibrate_noise_floor(self) -> dict:
        """Sample ambient noise to calibrate HOTWORD_MIN_RMS and VAD thresholds.

        Collects NOISE_CALIBRATION_SECONDS of audio after opening the stream,
        computes RMS statistics (mean, std, p95), then sets a per-environment
        noise floor. This prevents false wake/VAD triggers in noisy rooms
        AND ensures detection works in quiet environments.

        Returns calibration stats dict (always returns, even on failure).
        """
        duration = max(0.5, NOISE_CALIBRATION_SECONDS)
        n_frames = int((duration * 1000.0) / ((FRAME_SAMPLES / SAMPLE_RATE) * 1000.0))
        rms_samples: list[float] = []
        _safe_log(f"[NOISE_CAL] calibrating for {duration:.1f}s ({n_frames} frames) ...")
        for _ in range(n_frames):
            try:
                frame = self._frame_queue.get(timeout=0.3)
                rms, _peak = _calc_rms_peak(frame)
                if rms > 0.0:
                    rms_samples.append(rms)
            except queue.Empty:
                continue
        if len(rms_samples) < 3:
            _safe_log(f"[NOISE_CAL] too few samples ({len(rms_samples)}), using defaults")
            return {"calibrated": False, "rms_mean": 0.0, "rms_std": 0.0, "noise_floor": 0.0, "samples": len(rms_samples)}

        import statistics
        rms_mean = statistics.mean(rms_samples)
        rms_std = statistics.stdev(rms_samples) if len(rms_samples) > 1 else 0.0
        rms_p95 = sorted(rms_samples)[int(len(rms_samples) * 0.95)] if rms_samples else rms_mean
        noise_floor = max(rms_mean + NOISE_CALIBRATION_MULTIPLIER * rms_std, NOISE_CALIBRATION_MIN_RMS)
        noise_floor = min(noise_floor, NOISE_CALIBRATION_MAX_RMS)

        _safe_log(f"[NOISE_CAL] mean={rms_mean:.5f} std={rms_std:.5f} p95={rms_p95:.5f} floor={noise_floor:.5f} max={NOISE_CALIBRATION_MAX_RMS:.5f}")
        _safe_log(f"[NOISE_CAL] {len(rms_samples)} ambient samples collected")
        return {
            "calibrated": True,
            "rms_mean": rms_mean,
            "rms_std": rms_std,
            "rms_p95": rms_p95,
            "noise_floor": noise_floor,
            "samples": len(rms_samples),
        }

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
        if not _env_bool("OPENWAKEWORD_ENABLED", True):
            self.stop()
            self._last_start_error = "openwakeword_disabled"
            _safe_log("[WAKE] backend=openwakeword enabled=False")
            _safe_log("[HOTWORD] enabled=false")
            return
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

        # Adaptive noise calibration — samples ambient audio, adjusts thresholds
        # so the hotword and VAD work reliably in the current environment.
        cal = self.calibrate_noise_floor()
        if cal.get("calibrated"):
            import engine.audio_wake_pipeline as _mod
            old_min_rms = _mod.HOTWORD_MIN_RMS
            new_min_rms = cal["noise_floor"]
            _mod.HOTWORD_MIN_RMS = new_min_rms
            _safe_log(f"[NOISE_CAL] HOTWORD_MIN_RMS {old_min_rms:.5f} -> {new_min_rms:.5f}")
            # Also tune energy VAD threshold if we're using it.
            if hasattr(self._vad, "_rms_threshold"):
                old_vad = self._vad._rms_threshold
                new_vad = max(new_min_rms * 0.8, old_vad)
                if new_vad != old_vad:
                    self._vad._rms_threshold = new_vad
                    _safe_log(f"[NOISE_CAL] VAD RMS {old_vad:.5f} -> {new_vad:.5f}")
        else:
            _safe_log(f"[NOISE_CAL] ambient={cal.get('samples', 0)} samples — using env defaults")

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
            self._last_frame_time = time.time()
            if status:
                _safe_log(f"[MIC] callback_status={status}")
            try:
                pcm = (indata[:, 0] * 32767.0).clip(-32768, 32767).astype(np.int16).tobytes()
                self._frame_queue.put_nowait(pcm)
            except queue.Full:
                try:
                    self._frame_queue.get_nowait()
                    self._frame_queue.put_nowait(pcm)
                except Exception:
                    pass
            except Exception as exc:
                _safe_log(f"[MIC] callback_error={type(exc).__name__}")

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
        _hotword_log_interval = 5.0  # seconds between periodic hotword score logs
        _last_debug = 0.0
        _last_hw_log = 0.0
        _frame_count = 0
        while not self._stop_event.is_set():
            self._drain_control_events()
            # Microphone disconnect detection
            now = time.time()
            if self._last_frame_time > 0 and (now - self._last_frame_time) > 5.0:
                if not self._mic_disconnect_logged:
                    _safe_log("[MIC] DISCONNECTED — no audio frames for 5+ seconds")
                    self._mic_disconnect_logged = True
                # ponytail: retry forever with backoff. The old code capped at 3 attempts
                # and never reset the counter, so one unplug killed the mic (and hotword,
                # and the whole assistant) permanently until restart.
                backoff = min(30.0, 2.0 * (self._mic_reconnect_attempts + 1))
                if (now - self._last_frame_time) > 15.0 and (now - self._last_mic_retry) > backoff:
                    self._last_mic_retry = now
                    self._mic_reconnect_attempts += 1
                    _safe_log(f"[MIC] reconnect_attempt={self._mic_reconnect_attempts}")
                    try:
                        if self._stream is not None:
                            try:
                                self._stream.stop()
                                self._stream.close()
                            except Exception:
                                pass
                        self._stream = None
                        self._open_stream()
                        self._last_frame_time = time.time()
                        self._mic_disconnect_logged = False
                        _safe_log(f"[MIC] reconnected after {self._mic_reconnect_attempts} attempt(s)")
                        self._mic_reconnect_attempts = 0
                    except Exception as e:
                        _safe_log(f"[MIC] reconnect_failed reason={type(e).__name__}")
                time.sleep(0.2)  # ponytail: don't busy-spin while the mic is gone
                continue
            try:
                frame = self._frame_queue.get(timeout=0.2)
            except queue.Empty:
                if self._last_frame_time > 0 and (time.time() - self._last_frame_time) > 3.0:
                    if not self._mic_disconnect_logged:
                        _safe_log("[MIC] possible_disconnect — no frames in queue for 3+ seconds")
                        self._mic_disconnect_logged = True
                continue
            self._mic_disconnect_logged = False
            _frame_count += 1
            if WAKE_DEBUG and not self._audio_received_logged:
                _safe_log("[HOTWORD] audio_chunk_received=true")
                self._audio_received_logged = True
            try:
                result = self.process_frame(frame)
            except Exception as e:
                _safe_log(f"[WAKE] process_frame failed reason={type(e).__name__}")
                continue

            # Periodic logging of hotword scores (always on — needs no WAKE_DEBUG)
            now_hw = time.time()
            if now_hw - _last_hw_log >= _hotword_log_interval:
                _rms_hw, _peak_hw = _calc_rms_peak(frame)
                hw_score = result.get("score", 0.0)
                _safe_log(f"[HOTWORD] score={hw_score:.4f} rms={_rms_hw:.5f} hits={self._consecutive_hits}/{OWW_CONSECUTIVE} threshold={OWW_THRESHOLD} min_rms={_WAKE_RMS_FLOOR:.5f} reason={result.get('reason', 'none')}")
                _last_hw_log = now_hw

            # Periodic debug line so user sees the pipeline is alive.
            if WAKE_DEBUG:
                now_dbg = time.time()
                if now_dbg - _last_debug >= 1.0:
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
                self._dispatch_tts_watchdog_request()
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


def start_audio_wake_pipeline(on_command_text: Optional[Callable[[str], None]] = None, command_queue=None, control_queue=None) -> None:
    global _global_pipeline, _global_hotkey_listener, _last_start_error
    if not _env_bool("OPENWAKEWORD_ENABLED", True):
        stop_audio_wake_pipeline()
        _last_start_error = "openwakeword_disabled"
        _safe_log("[WAKE] backend=openwakeword enabled=False")
        _safe_log("[HOTWORD] enabled=false")
        return
    if _global_pipeline is not None and _global_pipeline.is_running:
        return
    _global_pipeline = AudioWakePipeline(
        on_command_text=on_command_text,
        command_queue=command_queue,
        control_queue=control_queue,
    )
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
