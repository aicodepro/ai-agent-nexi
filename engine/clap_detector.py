import os
import math
import struct
import time
import threading

# ---- Config (overridable via env) ----
def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


CLAP_DETECTION_ENABLED = _env_bool("NEXI_CLAP_ENABLED", _env_bool("CLAP_DETECTION_ENABLED", False))
CLAP_WAKE_MODE = os.getenv("CLAP_WAKE_MODE", "double")
CLAP_COOLDOWN_SECONDS = _env_int("NEXI_CLAP_COOLDOWN_MS", int(_env_float("CLAP_COOLDOWN_SECONDS", 2.0) * 1000)) / 1000.0
CLAP_WINDOW_SECONDS = float(os.getenv("CLAP_WINDOW_SECONDS", "0.8"))
CLAP_MIN_RMS = float(os.getenv("CLAP_MIN_RMS", "0.08"))
CLAP_PEAK_THRESHOLD = float(os.getenv("CLAP_PEAK_THRESHOLD", "0.35"))
CLAP_MIN_GAP_MS = _env_float("NEXI_CLAP_MIN_GAP_MS", _env_float("CLAP_MIN_GAP_MS", 180.0))
CLAP_MAX_GAP_MS = _env_float("NEXI_DOUBLE_CLAP_WINDOW_MS", _env_float("CLAP_MAX_GAP_MS", 4500.0))
CLAP_MAX_EVENT_MS = float(os.getenv("CLAP_MAX_EVENT_MS", "180"))
CLAP_NOISE_FLOOR_ALPHA = float(os.getenv("CLAP_NOISE_FLOOR_ALPHA", "0.95"))
CLAP_MAX_ACTIVE_RATIO = float(os.getenv("CLAP_MAX_ACTIVE_RATIO", "0.35"))
CLAP_MIN_CREST_FACTOR = float(os.getenv("CLAP_MIN_CREST_FACTOR", "1.8"))
CLAP_MODEL_PATH = os.getenv("CLAP_MODEL_PATH", "")
CLAP_SOURCE_PATH = os.getenv(
    "CLAP_SOURCE_PATH",
    r"E:\nexi-main\CLAP_NN-20260611T064455Z-3-001.zip",
)


def select_strategy() -> str:
    """Decide which detection strategy will be used.

    Returns:
        "clap_nn_model" if CLAP_NN model + deps are ready (Option A active),
        "rms_signal"    otherwise (Option C fallback, the default).
    """
    try:
        from engine.clap_model_adapter import is_model_available
    except Exception:
        return "rms_signal"
    return "clap_nn_model" if is_model_available() else "rms_signal"

SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
SAMPLE_WIDTH = 2


def _calc_rms_peak(frame: bytes, sample_width: int = SAMPLE_WIDTH):
    if sample_width == 2:
        fmt = "<{}h".format(len(frame) // 2)
        samples = struct.unpack(fmt, frame)
    else:
        return 0.0, 0.0
    if not samples:
        return 0.0, 0.0
    sum_sq = 0
    peak = 0
    for s in samples:
        sum_sq += s * s
        abs_s = abs(s)
        if abs_s > peak:
            peak = abs_s
    n = len(samples)
    rms = math.sqrt(sum_sq / n) / 32768.0
    peak_norm = peak / 32768.0
    return rms, peak_norm


def is_clap_frame(frame: bytes, sample_width: int = SAMPLE_WIDTH) -> bool:
    return is_clap_frame_with_noise(frame, noise_floor=0.0, sample_width=sample_width)


def is_clap_frame_with_noise(frame: bytes, noise_floor: float = 0.0, sample_width: int = SAMPLE_WIDTH) -> bool:
    rms, peak = _calc_rms_peak(frame, sample_width)
    if rms <= 0:
        return False
    threshold = max(CLAP_MIN_RMS, noise_floor * 4.0)
    if rms < threshold or peak < CLAP_PEAK_THRESHOLD:
        return False
    try:
        samples = struct.unpack("<{}h".format(len(frame) // 2), frame)
    except Exception:
        return False
    if not samples:
        return False
    active = sum(1 for s in samples if abs(s) / 32768.0 >= (CLAP_PEAK_THRESHOLD * 0.55))
    active_ratio = active / len(samples)
    crest = peak / max(rms, 1e-6)
    return active_ratio <= CLAP_MAX_ACTIVE_RATIO and crest >= CLAP_MIN_CREST_FACTOR


def detect_double_clap(events: list, now: float = None) -> bool:
    if now is None:
        now = time.time()
    if len(events) < 2:
        return False
    t1 = events[-2]
    t2 = events[-1]
    gap_ms = (t2 - t1) * 1000.0
    if CLAP_MIN_GAP_MS <= gap_ms <= CLAP_MAX_GAP_MS:
        return True
    if len(events) >= 3:
        t0 = events[-3]
        gap_ms_0 = (t1 - t0) * 1000.0
        if CLAP_MIN_GAP_MS <= gap_ms_0 <= CLAP_MAX_GAP_MS:
            return True
    return False


class ClapStateMachine:
    def __init__(self, clock=None):
        self._clock = clock or time.time
        self._events = []
        self._last_wake_at = 0.0
        self._noise_floor = 0.003
        self._state = "idle"
        self._active_event_started_at = None
        self._last_frame_at = None

    @property
    def state(self):
        return self._state

    @property
    def events(self):
        return list(self._events)

    @property
    def noise_floor(self):
        return self._noise_floor

    def reset(self):
        self._events = []
        self._state = "idle"
        self._active_event_started_at = None

    def process_model_clap(self, now: float | None = None) -> dict:
        if now is None:
            now = self._clock()
        return self._record_clap(now, 0.0, 0.0)

    def _base_event(self, clap=False, wake=False, cooldown=False, rms=0.0, peak=0.0, index=0, ignored=False, reason="", gap_ms=None):
        return {
            "clap": clap,
            "wake": wake,
            "cooldown": cooldown,
            "rms": rms,
            "peak": peak,
            "index": index,
            "state": self._state,
            "ignored": ignored,
            "reason": reason,
            "gap_ms": gap_ms,
        }

    def _record_clap(self, now: float, rms: float, peak: float) -> dict:
        if now - self._last_wake_at < CLAP_COOLDOWN_SECONDS:
            self._events = []
            self._state = "cooldown"
            return self._base_event(False, False, True, rms, peak, ignored=True, reason="long_audio_or_cooldown")

        self._events = [t for t in self._events if (now - t) * 1000.0 <= CLAP_MAX_GAP_MS]
        self._events.append(now)
        self._events = self._events[-2:]
        index = len(self._events)
        gap_ms = None
        if len(self._events) >= 2:
            gap_ms = (self._events[-1] - self._events[-2]) * 1000.0

        if CLAP_WAKE_MODE == "double" and detect_double_clap(self._events, now):
            self._last_wake_at = now
            self._events = []
            self._state = "wake_fired"
            return self._base_event(True, True, False, rms, peak, index=index, reason="double_clap", gap_ms=gap_ms)

        self._state = "first_clap_detected" if index == 1 else "waiting_for_second"
        return self._base_event(True, False, False, rms, peak, index=index, reason="single_clap", gap_ms=gap_ms)

    def process_frame(self, frame: bytes) -> dict:
        now = self._clock()
        rms, peak = _calc_rms_peak(frame)
        is_clap = is_clap_frame_with_noise(frame, noise_floor=self._noise_floor)
        previous_frame_at = self._last_frame_at
        self._last_frame_at = now
        if not is_clap:
            alpha = max(0.0, min(0.999, CLAP_NOISE_FLOOR_ALPHA))
            self._noise_floor = (self._noise_floor * alpha) + (min(rms, 0.05) * (1.0 - alpha))
            self._events = [t for t in self._events if (now - t) * 1000.0 <= CLAP_MAX_GAP_MS]
            self._active_event_started_at = None
            if not self._events and self._state != "cooldown":
                self._state = "idle"
            return self._base_event(False, False, False, rms, peak)

        if self._active_event_started_at is not None:
            frame_gap_ms = 0.0
            if previous_frame_at is not None:
                frame_gap_ms = (now - previous_frame_at) * 1000.0
            if frame_gap_ms <= CLAP_MAX_EVENT_MS:
                return self._base_event(False, False, False, rms, peak, ignored=True, reason="long_audio_or_cooldown")

        self._active_event_started_at = now
        return self._record_clap(now, rms, peak)


class ClapListener:
    def __init__(self, on_wake_callback=None):
        self._on_wake_callback = on_wake_callback
        self._thread = None
        self._running = False
        self._clap_events = []
        self._last_wake_at = 0.0
        self._model_detector = None
        self._strategy = "rms_signal"
        self._state = ClapStateMachine()

    @property
    def enabled(self) -> bool:
        return CLAP_DETECTION_ENABLED

    def _is_clap(self, frame: bytes) -> bool:
        """Per-frame clap decision. Uses CLAP_NN model if loaded, else RMS.

        A model exception is non-fatal: we fall back to RMS for that
        frame so the listener loop survives any inference hiccup.
        """
        if self._model_detector is not None:
            try:
                is_clap, _conf = self._model_detector.predict_pcm16(frame, SAMPLE_RATE)
                return bool(is_clap)
            except Exception as e:
                print(f"[CLAP] model_predict failed reason={type(e).__name__}; falling back to rms for this frame")
        return is_clap_frame(frame)

    def _init_strategy(self) -> None:
        """Pick CLAP_NN model if available, otherwise RMS signal detector.
        Logged once at startup. Never raises."""
        self._strategy = "rms_signal"
        self._model_detector = None
        try:
            from engine.clap_model_adapter import try_load_model_detector
            det = try_load_model_detector()
            if det is not None:
                self._model_detector = det
                self._strategy = "clap_nn_model"
        except Exception as e:
            print(f"[CLAP] model_adapter unavailable reason={type(e).__name__}")
        print(f"[CLAP] strategy={self._strategy}")

    def start(self):
        if not self.enabled:
            print("[CLAP] disabled")
            return
        if self._running:
            return
        try:
            import pyaudio
        except ImportError:
            print("[CLAP] unavailable — missing dependency: pyaudio")
            return
        self._init_strategy()
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        print("[CLAP] state=idle")
        print("[CLAP] listening")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _listen_loop(self):
        import pyaudio as _pa
        try:
            audio = _pa.PyAudio()
            stream = audio.open(
                format=_pa.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )
        except Exception as e:
            print(f"[CLAP] unavailable — microphone error: {e}")
            self._running = False
            return

        while self._running:
            try:
                frame = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                if self._model_detector is not None and self._is_clap(frame):
                    event = self._state.process_model_clap(time.time())
                else:
                    event = self._state.process_frame(frame)
                if event.get("ignored"):
                    print(f"[CLAP] ignored reason={event.get('reason', 'long_audio_or_cooldown')}")
                if event.get("clap"):
                    print(f"[CLAP] clap_{event.get('index', 1)} rms={event.get('rms', 0):.3f} peak={event.get('peak', 0):.3f} strategy={self._strategy}")
                if event.get("cooldown"):
                    print("[CLAP] cooldown active")
                    continue
                if event.get("wake"):
                    print("[CLAP] wake detected mode=double")
                    if self._on_wake_callback:
                        self._on_wake_callback()
            except Exception as e:
                print(f"[CLAP] error: {e}")
                time.sleep(0.1)

        try:
            stream.stop_stream()
            stream.close()
            audio.terminate()
        except Exception:
            pass


def is_any_clap_frame(frame: bytes, sample_width: int = SAMPLE_WIDTH) -> bool:
    return is_clap_frame(frame, sample_width)


def start_clap_listener(on_wake_callback=None):
    listener = ClapListener(on_wake_callback=on_wake_callback)
    listener.start()
    return listener


def stop_clap_listener(listener):
    if listener:
        listener.stop()
