"""Clap backend manager — primary CLAP_NN adapter.

Controls:
   NEXI_CLAP_ENABLED=true              master switch
   NEXI_CLAP_PRIMARY=clap_nn           primary backend (clap_nn|yamnet|dsp_clap|tzur|nexi)
   NEXI_CLAP_FALLBACK=                 fallback if primary fails/unavailable
   NEXI_CLAP_BACKEND_ORDER=                 ordered priority list (comma-separated)
  NEXI_CLAP_DEBUG=true                enable per-chunk debug logging
  NEXI_CLAP_PATTERN=double            pattern to trigger wake (double)
  NEXI_CLAP_COOLDOWN_MS=1500          cooldown between wake events
"""

from __future__ import annotations

import os
import time
from typing import Optional


MIN_EFFECTIVE_MAX_GAP_MS = 4500.0


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


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


class ClapBackendManager:
    def __init__(self, *, clock: Optional[callable] = None, cooldown_ms: int | None = None):
        self._clock = clock or time.time
        self._primary_name = ""
        self._fallback_name = ""
        self._primary = None
        self._fallback = None
        self._primary_ready = False
        self._fallback_ready = False
        self._last_wake_at = 0.0
        self._cooldown_ms = _env_int(
            "NEXI_CLAP_COOLDOWN_MS", _env_int("JARVIS_CLAP_COOLDOWN_MS", 1500)
        ) if cooldown_ms is None else int(cooldown_ms)
        self._debug = _env_bool("NEXI_CLAP_DEBUG", False)

        self._min_gap_ms = _env_float(
            "NEXI_CLAP_MIN_GAP_MS",
            _env_float("CLAP_MIN_GAP_MS", _env_float("JARVIS_CLAP_MIN_GAP_MS", 100.0)),
        )
        self._configured_max_gap_ms = _env_float(
            "NEXI_CLAP_MAX_GAP_MS",
            _env_float("CLAP_MAX_GAP_MS", _env_float("JARVIS_CLAP_MAX_GAP_MS", 3500.0)),
        )
        self._max_gap_ms = max(MIN_EFFECTIVE_MAX_GAP_MS, self._configured_max_gap_ms)
        self._double_clap = None

        self._init_backends()

    def _init_backends(self) -> None:
        configured_order = os.getenv("NEXI_CLAP_BACKEND_ORDER", os.getenv("JARVIS_CLAP_BACKEND_ORDER", "dsp_clap,clap_nn"))
        order = [item.strip() for item in (configured_order or "dsp_clap,clap_nn").split(",") if item.strip()]
        primary = order[0] if order else (os.getenv("NEXI_CLAP_PRIMARY", os.getenv("JARVIS_CLAP_PRIMARY", "dsp_clap")) or "dsp_clap").strip()
        fallback = order[1] if len(order) > 1 else (os.getenv("NEXI_CLAP_FALLBACK", os.getenv("JARVIS_CLAP_FALLBACK", "")) or "").strip()

        self._primary_name = primary
        self._fallback_name = fallback

        if primary == "clap_nn":
            self._primary, self._primary_ready = self._build_clap_nn()
        elif primary == "yamnet":
            self._primary, self._primary_ready = self._build_yamnet()
        elif primary == "dsp_clap":
            self._primary = self._build_dsp_clap()
            self._primary_ready = self._primary is not None
        elif primary == "tzur":
            self._primary = self._build_tzur()
            self._primary_ready = self._primary is not None
        elif primary == "nexi":
            self._primary, self._primary_ready = self._build_nexi()

        if not self._primary_ready:
            if fallback == "clap_nn":
                self._fallback, self._fallback_ready = self._build_clap_nn()
            elif fallback == "yamnet":
                self._fallback, self._fallback_ready = self._build_yamnet()
            elif fallback == "dsp_clap":
                self._fallback = self._build_dsp_clap()
                self._fallback_ready = self._fallback is not None
            elif fallback == "nexi":
                self._fallback, self._fallback_ready = self._build_nexi()
            elif fallback == "tzur":
                self._fallback = self._build_tzur()
                self._fallback_ready = self._fallback is not None

        configured_primary = primary
        active_backend = ""
        if self._primary_ready:
            active_backend = primary
        elif self._fallback_ready:
            active_backend = fallback
        else:
            active_backend = "none"
        reason = ""
        if not self._primary_ready:
            if primary == "yamnet":
                reason = "yamnet_not_ready"
            elif primary == "clap_nn":
                reason = "clap_nn_not_ready"
            else:
                reason = f"{primary}_not_ready"
        print(f"[CLAP_MGR] configured_primary={configured_primary}", flush=True)
        print(f"[CLAP_MGR] active_backend={active_backend} reason={reason}", flush=True)
        if self._max_gap_ms > self._configured_max_gap_ms:
            print(f"[CLAP_CONFIG] legacy_max_gap_ms={self._configured_max_gap_ms} raised_to_ms={self._max_gap_ms}", flush=True)
        if self._debug:
            print(f"[CLAP_MGR] primary={primary} ready={self._primary_ready} "
                  f"fallback={fallback} ready={self._fallback_ready}", flush=True)
        print(f"[CLAP_CONFIG] min_gap_ms={self._min_gap_ms} max_gap_ms={self._max_gap_ms} cooldown_ms={self._cooldown_ms} backend={active_backend}", flush=True)

    def _build_clap_nn(self) -> tuple:
        try:
            from engine.clap_nn_backend import ClapNNBackend
            model_path = os.getenv("NEXI_CLAP_NN_MODEL_PATH", "")
            if not model_path:
                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                model_path = os.path.join(base, "external", "CLAP_NN",
                                           "ASSETS", "CLAP_DETECTS", "MODELS", "Clap_Detect_Model.pth")
                # Fallback to old path
                old_path = os.path.join(base, "external", "CLAP_NN_INSPECT", "CLAP_NN",
                                         "ASSETS", "CLAP_DETECTS", "MODELS", "Clap_Detect_Model.pth")
                if not os.path.isfile(model_path) and os.path.isfile(old_path):
                    model_path = old_path
            backend = ClapNNBackend(model_path=model_path)
            ready = backend._ready
            if not ready:
                print(f"[CLAP_NN] not_ready reason=model_missing path={model_path}", flush=True)
            return backend, ready
        except Exception as e:
            print(f"[CLAP_NN] not_ready reason={type(e).__name__}", flush=True)
            return None, False

    def _build_yamnet(self) -> tuple:
        try:
            from engine.yamnet_clap_backend import YamnetClapBackend
            backend = YamnetClapBackend()
            ready = backend.ready
            if not ready:
                print(f"[YAMNET] not_ready reason={backend._load_error}", flush=True)
            return backend, ready
        except Exception as e:
            print(f"[YAMNET] not_ready reason={type(e).__name__}", flush=True)
            return None, False

    def _build_dsp_clap(self):
        try:
            from engine.dsp_clap_backend import DspClapBackend
            return DspClapBackend()
        except Exception as e:
            print(f"[DSP_CLAP] init_failed reason={type(e).__name__}", flush=True)
            return None

    def _build_tzur(self):
        try:
            from engine.tzur_clap_adapter import TzurClapAdapter
            return TzurClapAdapter(
                sample_rate=16000,
                clock=self._clock,
                min_clap_gap_ms=_env_float("NEXI_CLAP_MIN_GAP_MS", _env_float("CLAP_MIN_GAP_MS", 180.0)),
                max_clap_gap_ms=max(MIN_EFFECTIVE_MAX_GAP_MS, _env_float("NEXI_DOUBLE_CLAP_WINDOW_MS", _env_float("CLAP_MAX_GAP_MS", 3500.0))),
            )
        except Exception as e:
            print(f"[CLAP_MGR] tzur_init_failed reason={type(e).__name__}", flush=True)
            return None

    def _build_nexi(self) -> tuple:
        try:
            from engine.clap_detector import ClapStateMachine
            sm = ClapStateMachine(clock=self._clock)
            return sm, True
        except Exception as e:
            print(f"[CLAP_MGR] nexi_init_failed reason={type(e).__name__}", flush=True)
            return None, False

    @property
    def primary_ready(self) -> bool:
        return self._primary_ready

    @property
    def fallback_ready(self) -> bool:
        return self._fallback_ready

    @property
    def primary_name(self) -> str:
        return self._primary_name

    @property
    def fallback_name(self) -> str:
        return self._fallback_name

    def get_status(self) -> dict:
        dc_state = self._double_clap.get_status() if self._double_clap else {}
        return {
            "primary": self._primary_name,
            "primary_ready": self._primary_ready,
            "fallback": self._fallback_name,
            "fallback_ready": self._fallback_ready,
            "cooldown_ms": self._cooldown_ms,
            "min_gap_ms": self._min_gap_ms,
            "max_gap_ms": self._max_gap_ms,
            "double_clap_state": dc_state.get("state", "unknown"),
            "waiting_for_second_clap": dc_state.get("state") in ("stage_first_clap", "first_clap_waiting"),
        }

    def get_debug_snapshot(self) -> dict:
        snap = self.get_status()
        if self._primary is not None and hasattr(self._primary, "get_debug_snapshot"):
            snap["primary_stats"] = self._primary.get_debug_snapshot()
        return snap

    def _init_double_clap(self) -> None:
        if self._double_clap is not None:
            return
        try:
            from engine.dsp_clap_backend import DoubleClapDetector
            self._double_clap = DoubleClapDetector(
                clock=self._clock,
                min_gap_ms=int(self._min_gap_ms),
                max_gap_ms=int(self._max_gap_ms),
                cooldown_ms=self._cooldown_ms,
            )
        except Exception as e:
            print(f"[CLAP_MGR] double_clap_init_failed reason={type(e).__name__}", flush=True)
            self._double_clap = None

    def _apply_double_clap_state(self, result: dict, now: float) -> dict:
        """Apply double-clap state machine using DoubleClapDetector."""
        self._init_double_clap()
        if self._double_clap is None:
            return result

        if not result.get("clap"):
            return result

        dd_result = self._double_clap.detect(now)
        result["wake"] = dd_result["wake"]
        result["source"] = "double_clap" if dd_result["wake"] else None
        result["gap_ms"] = dd_result["gap_ms"]
        result["reject_reason"] = dd_result["reason"] if not dd_result["wake"] else ""
        result["double_clap_state"] = dd_result["state"]

        if dd_result["wake"]:
            self._last_wake_at = now
            if self._debug:
                self._log_detection("double_clap", self._primary_name, result)
                print(f"[CLAP] double_clap_detected=true backend={result.get('backend_used')} wake=true", flush=True)
        elif dd_result["clap"] and self._debug:
            print(f"[CLAP] first_clap state={dd_result['state']} wake=false", flush=True)

        return result

    def process_audio_chunk(self, frame_int16: bytes) -> dict:
        """Process one audio chunk through the primary backend, falling back
        to Nexi if the primary is unavailable or fails.

        Double-clap detection is done via DoubleClapDetector.
        Individual backends only report is_clap; wake is decided here.

        Returns:
            wake: bool      — double clap pattern detected
            clap: bool      — single clap detected (may not trigger wake)
            source: str|None
            backend: str     — which backend produced the result
            backend_used: str
            fallback_used: bool
        """
        now = self._clock()

        from engine.wake_session_manager import get_session_manager
        get_session_manager().check_timeout()
        self._init_double_clap()

        # Check global cooldown
        if self._cooldown_ms > 0:
            if self._last_wake_at > 0 and now - self._last_wake_at < self._cooldown_ms / 1000.0:
                result = {"wake": False, "clap": False, "source": None,
                          "backend": "cooldown", "backend_used": "cooldown",
                          "fallback_used": False, "cooldown": True,
                          "reason": "cooldown", "reject_reason": "cooldown"}
                if self._debug:
                    print(f"[CLAP] cooldown remaining_ms={(self._cooldown_ms/1000 - (now - self._last_wake_at))*1000:.0f}", flush=True)
                return result

        # Try primary
        result: dict = {}
        if self._primary_ready:
            raw = self._try_backend(self._primary, self._primary_name, frame_int16)
            if raw.get("clap"):
                result = self._apply_double_clap_state(raw, now)
                if result.get("wake"):
                    if self._debug:
                        self._log_detection("primary", self._primary_name, result)
                    return result
                if result.get("clap"):
                    # single clap — return without waking
                    return result

        # Try fallback
        if self._fallback_ready and not result:
            raw = self._try_backend(self._fallback, self._fallback_name, frame_int16)
            raw["fallback_used"] = True
            if raw.get("clap"):
                result = self._apply_double_clap_state(raw, now)
                if result.get("wake"):
                    if self._debug:
                        self._log_detection("fallback", self._fallback_name, result)
                    return result

        if result:
            return result

        last_reason = "backend_not_ready"
        try:
            if self._primary is not None and hasattr(self._primary, "get_debug_snapshot"):
                stats = self._primary.get_debug_snapshot() or {}
                last_reason = ((stats.get("last_result") or {}).get("reason") or last_reason)
        except Exception:
            pass
        return {"wake": False, "clap": False, "source": None,
                "backend": "none", "backend_used": "none",
                "fallback_used": bool(self._fallback_ready and not self._primary_ready),
                "cooldown": False, "reason": last_reason, "reject_reason": last_reason}

    def _try_backend(self, backend, name: str, frame: bytes) -> dict:
        try:
            if name == "clap_nn":
                return self._wrap_clap_nn(backend.process_pcm16(frame, self._clock()))
            elif name == "yamnet":
                return self._wrap_yamnet(backend.process_pcm16(frame, self._clock()))
            elif name == "dsp_clap":
                return self._wrap_dsp_clap(backend.process_pcm16(frame, self._clock()))
            elif name == "tzur":
                return self._wrap_tzur(backend.process_audio_chunk(frame))
            elif name == "nexi":
                return self._wrap_nexi(backend.process_frame(frame))
        except Exception as e:
            print(f"[CLAP_MGR] backend={name} error reason={type(e).__name__}", flush=True)
        return {"wake": False, "clap": False, "source": None}

    def _wrap_clap_nn(self, result: 'ClapNNResult') -> dict:
        is_clap = bool(result.is_clap)
        return {
            "wake": False,  # wake is decided by double-clap state machine
            "clap": is_clap,
            "source": None,
            "backend": "clap_nn",
            "backend_used": "clap_nn",
            "fallback_used": False,
            "cooldown": False,
            "amplitude": result.rms,
            "threshold": result.confidence,
            "gap_ms": None,
            "reason": result.reason,
            "pattern": [],
        }

    def _wrap_yamnet(self, result: 'YamnetClapResult') -> dict:
        is_clap = bool(result.is_clap)
        return {
            "wake": False,
            "clap": is_clap,
            "source": None,
            "backend": "yamnet",
            "backend_used": "yamnet",
            "fallback_used": False,
            "cooldown": False,
            "amplitude": result.confidence,
            "threshold": 0.0,
            "gap_ms": None,
            "reason": result.reason,
            "pattern": [],
        }

    def _wrap_dsp_clap(self, result: 'DspClapResult') -> dict:
        is_clap = bool(result.is_clap)
        return {
            "wake": False,
            "clap": is_clap,
            "source": None,
            "backend": "dsp_clap",
            "backend_used": "dsp_clap",
            "fallback_used": False,
            "cooldown": False,
            "amplitude": result.rms,
            "threshold": 0.0,
            "gap_ms": None,
            "reason": result.reason,
            "pattern": [],
        }

    def _wrap_tzur(self, raw: dict) -> dict:
        return {
            "wake": raw.get("wake", False),
            "clap": raw.get("clap", False),
            "source": "double_clap" if raw.get("wake") else None,
            "backend": "tzur",
            "backend_used": "tzur",
            "fallback_used": False,
            "cooldown": raw.get("cooldown", False),
            "amplitude": raw.get("amplitude", 0.0),
            "threshold": raw.get("threshold", 0.0),
            "gap_ms": raw.get("gap_ms"),
            "reason": raw.get("reason", ""),
            "pattern": raw.get("pattern", []),
        }

    def _wrap_nexi(self, raw: dict) -> dict:
        return {
            "wake": raw.get("wake", False),
            "clap": raw.get("clap", False),
            "source": "double_clap" if raw.get("wake") else None,
            "backend": "nexi",
            "backend_used": "nexi",
            "fallback_used": False,
            "cooldown": raw.get("cooldown", False),
            "amplitude": 0.0,
            "threshold": 0.0,
            "gap_ms": raw.get("gap_ms"),
            "reason": raw.get("reason", ""),
            "pattern": raw.get("pattern", []),
        }

    def _log_detection(self, tier: str, name: str, result: dict) -> None:
        print(f"[CLAP_MGR] wake tier={tier} backend={name} "
              f"clap={result.get('clap')} wake={result.get('wake')}", flush=True)

    def reset(self) -> None:
        if self._primary is not None and hasattr(self._primary, "reset"):
            self._primary.reset()
        if self._fallback is not None and hasattr(self._fallback, "reset"):
            if isinstance(self._fallback, tuple):
                pass
            else:
                self._fallback.reset()
        self._last_wake_at = 0.0
        if self._double_clap is not None:
            self._double_clap.reset()


def create_backend_manager(cooldown_ms: int = 1500) -> ClapBackendManager:
    ms = int(os.getenv("NEXI_CLAP_COOLDOWN_MS", str(cooldown_ms or 1500)))
    return ClapBackendManager(cooldown_ms=ms)
