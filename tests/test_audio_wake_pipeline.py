import os
import struct
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _silent_frame(n_samples: int = 1280) -> bytes:
    return b"\x00\x00" * n_samples


def _loud_frame(n_samples: int = 1280, amp: int = 30000) -> bytes:
    samples = [0] * (n_samples // 2) + [amp] * (n_samples // 4) + [0] * (n_samples - 3 * (n_samples // 4))
    return struct.pack(f"<{len(samples)}h", *samples)


class FakeClock:
    def __init__(self, start: float = 1_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class ScriptedScorer:
    """Returns scores from a pre-set list, cycling through."""

    def __init__(self, scores):
        self.scores = list(scores)
        self.idx = 0
        self.name = "scripted"

    def score(self, frame: bytes) -> float:
        if not self.scores:
            return 0.0
        s = self.scores[min(self.idx, len(self.scores) - 1)]
        self.idx += 1
        return float(s)


class ScriptedVAD:
    """Returns is_speech from a pre-set list, cycling through."""

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.idx = 0
        self.name = "scripted"

    def is_speech(self, frame: bytes) -> bool:
        if not self.decisions:
            return False
        d = self.decisions[min(self.idx, len(self.decisions) - 1)]
        self.idx += 1
        return bool(d)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.setenv("VOICE_WAKE_BACKEND", "openwakeword")
    monkeypatch.setenv("OPENWAKEWORD_ENABLED", "true")
    monkeypatch.setenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.65")
    monkeypatch.setenv("OPENWAKEWORD_CONSECUTIVE_HITS", "2")
    monkeypatch.setenv("WAKE_COOLDOWN_SECONDS", "2.0")
    monkeypatch.setenv("CLAP_DETECTION_ENABLED", "false")
    monkeypatch.delenv("NEXI_CLAP_ENABLED", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("NEXI_WAKE_SOURCES", "hotword,double_clap,hotkey")
    monkeypatch.setenv("NEXI_HOTKEY_WAKE_ENABLED", "false")
    monkeypatch.setenv("NEXI_HOTKEY_ENABLED", "false")
    # Reset session manager state between tests.
    from engine.wake_session_manager import WakeSessionManager
    mgr = WakeSessionManager.get_instance()
    mgr._session_id = None
    mgr._source = ""
    mgr._state = "sleep"
    mgr._detectors_paused = False
    mgr._started_at = 0.0
    mgr._last_event_at = 0.0
    # Reload module so env values are picked up.
    import importlib
    import engine.audio_wake_pipeline as awp
    importlib.reload(awp)
    yield


def _fresh_pipeline(**kwargs):
    """Build a pipeline with sensible test defaults."""
    from engine.audio_wake_pipeline import AudioWakePipeline
    kwargs.setdefault("clock", FakeClock())
    return AudioWakePipeline(**kwargs)


# ---------------------------------------------------------------------------
# Dependency / startup behaviour
# ---------------------------------------------------------------------------

def test_openwakeword_missing_does_not_crash(monkeypatch, capsys):
    """If openwakeword fails to import, start() must log a safe line
    and the pipeline must not crash the process."""
    from engine.audio_wake_pipeline import AudioWakePipeline

    pipeline = AudioWakePipeline()

    # Patch the lazy import so OpenWakeWordScorer.__init__ raises ImportError.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openwakeword.model":
            raise ImportError("simulated missing openwakeword")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        # Also patch sounddevice to not actually open a mic.
        with patch("sounddevice.InputStream", side_effect=ImportError("no sd")):
            pipeline.start()  # must not raise

    assert pipeline.is_running is False
    out = capsys.readouterr().out
    assert "openwakeword unavailable" in out or "mic_unavailable" in out


def test_pipeline_disabled_does_not_start(monkeypatch, capsys):
    monkeypatch.setenv("OPENWAKEWORD_ENABLED", "false")
    import importlib
    import engine.audio_wake_pipeline as awp
    importlib.reload(awp)

    pipeline = awp.AudioWakePipeline()
    pipeline.start()
    assert pipeline.is_running is False
    out = capsys.readouterr().out
    assert "enabled=False" in out


def test_module_level_start_stop_works_when_disabled(monkeypatch):
    monkeypatch.setenv("OPENWAKEWORD_ENABLED", "false")
    import importlib
    import engine.audio_wake_pipeline as awp
    importlib.reload(awp)

    awp.start_audio_wake_pipeline()
    assert awp.is_pipeline_running() is False
    awp.stop_audio_wake_pipeline()  # must not raise


# ---------------------------------------------------------------------------
# Wake detection: consecutive hits + cooldown
# ---------------------------------------------------------------------------

def test_hotword_score_threshold_requires_consecutive_hits():
    """One above-threshold frame must NOT wake; N consecutive frames must."""
    clock = FakeClock()
    # threshold=0.65, consecutive=2 from env
    scorer = ScriptedScorer([0.9, 0.1, 0.9, 0.9])
    pipeline = _fresh_pipeline(wake_scorer=scorer, clock=clock)

    r1 = pipeline.process_frame(_silent_frame())  # 0.9 -> hit #1, no wake
    assert r1["wake"] is False
    r2 = pipeline.process_frame(_silent_frame())  # 0.1 -> reset
    assert r2["wake"] is False
    r3 = pipeline.process_frame(_silent_frame())  # 0.9 -> hit #1 (reset earlier)
    assert r3["wake"] is False
    r4 = pipeline.process_frame(_silent_frame())  # 0.9 -> hit #2 -> WAKE
    assert r4["wake"] is True
    assert r4["source"] == "hotword"


def test_cooldown_blocks_repeat_wake():
    clock = FakeClock()
    scorer = ScriptedScorer([0.9] * 10)
    pipeline = _fresh_pipeline(wake_scorer=scorer, clock=clock)

    # First wake: frames 1+2
    pipeline.process_frame(_silent_frame())
    r2 = pipeline.process_frame(_silent_frame())
    assert r2["wake"] is True

    # Without advancing the clock, another two hits should be cooldown-blocked.
    pipeline.process_frame(_silent_frame())
    r4 = pipeline.process_frame(_silent_frame())
    assert r4["wake"] is False
    assert r4["cooldown"] is True

    # Advance past cooldown; next two hits wake again.
    clock.advance(3.0)
    pipeline.process_frame(_silent_frame())
    r6 = pipeline.process_frame(_silent_frame())
    assert r6["wake"] is True


# ---------------------------------------------------------------------------
# Clap path
# ---------------------------------------------------------------------------

def test_clap_disabled_by_default(monkeypatch):
    monkeypatch.setenv("CLAP_DETECTION_ENABLED", "false")
    monkeypatch.setenv("NEXI_CLAP_ENABLED", "false")
    # Reload clap_detector to honour env, then build pipeline.
    import importlib
    import engine.clap_detector as cd
    importlib.reload(cd)
    pipeline = _fresh_pipeline(wake_scorer=ScriptedScorer([0.0] * 10))
    assert pipeline.is_clap_enabled() is False


def test_double_clap_callback_path(monkeypatch):
    """Two loud claps inside CLAP_MIN_GAP_MS..CLAP_MAX_GAP_MS must wake."""
    monkeypatch.setenv("CLAP_DETECTION_ENABLED", "true")
    monkeypatch.setenv("NEXI_CLAP_ENABLED", "true")
    monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "tzur,nexi")
    import importlib
    import engine.clap_detector as cd
    importlib.reload(cd)

    clock = FakeClock()
    # Wake scorer returns 0 -> never trips the hotword path.
    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0] * 10),
        clock=clock,
        enable_clap=True,
    )

    # First clap.
    r1 = pipeline.process_frame(_loud_frame())
    assert r1["wake"] is False  # one clap alone

    # Advance 300 ms (inside the configured 120..800 ms window).
    clock.advance(0.30)
    r2 = pipeline.process_frame(_loud_frame())
    assert r2["wake"] is True
    assert r2["source"] == "double_clap"


def test_single_clap_does_not_wake(monkeypatch):
    monkeypatch.setenv("CLAP_DETECTION_ENABLED", "true")
    monkeypatch.setenv("NEXI_CLAP_ENABLED", "true")
    import importlib
    import engine.clap_detector as cd
    importlib.reload(cd)

    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0] * 10),
        enable_clap=True,
    )
    result = pipeline.process_frame(_loud_frame())
    assert result["wake"] is False


def test_double_clap_wakes_once(monkeypatch):
    monkeypatch.setenv("CLAP_DETECTION_ENABLED", "true")
    monkeypatch.setenv("NEXI_CLAP_ENABLED", "true")
    monkeypatch.setenv("NEXI_CLAP_BACKEND_ORDER", "tzur,nexi")
    import importlib
    import engine.clap_detector as cd
    importlib.reload(cd)

    clock = FakeClock()
    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0] * 10),
        clock=clock,
        enable_clap=True,
    )
    pipeline.process_frame(_loud_frame())
    clock.advance(0.30)
    first = pipeline.process_frame(_loud_frame())
    clock.advance(0.30)
    second = pipeline.process_frame(_loud_frame())
    assert first["wake"] is True
    assert second["wake"] is False


def test_clap_enabled_in_pipeline_path(monkeypatch):
    monkeypatch.setenv("CLAP_DETECTION_ENABLED", "true")
    monkeypatch.setenv("NEXI_CLAP_ENABLED", "true")
    import importlib
    import engine.clap_detector as cd
    importlib.reload(cd)

    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0] * 10),
        enable_clap=True,
    )
    assert pipeline.is_clap_enabled() is True


# ---------------------------------------------------------------------------
# ASR / command dispatch
# ---------------------------------------------------------------------------

def test_empty_transcript_does_not_call_allCommands():
    called = []

    def fake_on_command(text):
        called.append(text)

    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0]),
        on_command_text=fake_on_command,
        asr=lambda audio, sr: "",  # ASR returns empty
    )
    result = pipeline.emit_command(b"\x00\x00" * 1600)
    assert result == ""
    assert called == []  # default handler NOT called for empty transcript


def test_transcript_calls_allCommands_once():
    calls = []

    def fake_on_command(text):
        calls.append(text)

    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0]),
        on_command_text=fake_on_command,
        asr=lambda audio, sr: "what is 2+2",
    )
    result = pipeline.emit_command(b"\x00\x00" * 1600)
    assert result == "what is 2+2"
    assert calls == ["what is 2+2"]


def test_default_handler_calls_allCommands(monkeypatch):
    """When no on_command_text is provided, transcript routes through
    engine.command.allCommands exactly once."""
    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0]),
        on_command_text=None,
        asr=lambda audio, sr: "open chrome",
    )
    with patch("engine.command.allCommands") as mock_all:
        pipeline.emit_command(b"\x00\x00" * 1600)
        mock_all.assert_called_once_with("open chrome")


# ---------------------------------------------------------------------------
# VAD command capture
# ---------------------------------------------------------------------------

def test_capture_command_stops_on_silence():
    """speech_started then enough silence frames -> capture ends."""
    # 8 speech frames so speech_frames >= min_speech_frames (5 at 80ms/frame).
    speech = _loud_frame()
    silence = _silent_frame()
    frames = [speech] * 8 + [silence] * 100

    it = iter(frames)
    def next_frame():
        try:
            return next(it)
        except StopIteration:
            return None

    vad = ScriptedVAD([True] * 8 + [False] * 100)
    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0]),
        vad=vad,
        asr=lambda a, s: "",
    )
    captured = pipeline.capture_command(next_frame)
    assert len(captured) > 0
    # Stopped by silence threshold well before 108-frame end.
    assert vad.idx < 108


def test_capture_command_stops_on_max_duration():
    """Even with no silence, capture stops after VAD_MAX_COMMAND_SECONDS."""
    speech = _loud_frame()
    it = iter([speech] * 10000)
    def next_frame():
        try:
            return next(it)
        except StopIteration:
            return None

    vad = ScriptedVAD([True] * 10000)
    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0]),
        vad=vad,
        asr=lambda a, s: "",
    )
    captured = pipeline.capture_command(next_frame)
    # We bounded the capture; consumed less than the full source.
    assert vad.idx < 10000


def test_wake_tail_flush_before_command_capture():
    from engine.audio_wake_pipeline import FRAME_SAMPLES, SAMPLE_RATE, WAKE_FLUSH_AUDIO_MS
    pipeline = _fresh_pipeline(wake_scorer=ScriptedScorer([0.0]))
    expected_frames = max(0, int((WAKE_FLUSH_AUDIO_MS / 1000.0) * SAMPLE_RATE / FRAME_SAMPLES))
    for _ in range(expected_frames + 2):
        pipeline._frame_queue.put_nowait(_silent_frame())
    pipeline._preroll.append(_loud_frame())

    drained = pipeline.flush_wake_tail()

    assert drained == expected_frames
    assert len(pipeline._preroll) == 0
    assert pipeline._frame_queue.qsize() == 2


# ---------------------------------------------------------------------------
# Bug regression: emit_command must call ASR exactly once
# ---------------------------------------------------------------------------

def test_asr_called_once_per_emit():
    """The ASR function must be called exactly once per emit_command invocation.
    Regression for the duplicate [ASR] request_started log."""
    call_count = []

    def counting_asr(audio, sr):
        call_count.append(1)
        return "hello"

    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0]),
        on_command_text=lambda t: None,
        asr=counting_asr,
    )
    pipeline.emit_command(b"\x00\x00" * 1600)
    assert len(call_count) == 1


def test_transcript_emitted_once():
    """Same as the existing test, but verifies the exact call count is 1."""
    calls = []
    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0]),
        on_command_text=lambda t: calls.append(t),
        asr=lambda a, s: "open chrome",
    )
    pipeline.emit_command(b"\x00\x00" * 1600)
    assert calls == ["open chrome"]


# ---------------------------------------------------------------------------
# Bug regression: allCommands must survive missing eel functions
# ---------------------------------------------------------------------------

def test_allCommands_does_not_crash_when_eel_senderText_missing():
    """In Process 2 (wake pipeline), eel JS functions are not exposed.
    allCommands must not crash with AttributeError on senderText."""
    import engine.command as command

    mock_eel = MagicMock()
    # Simulate missing senderText attribute — getattr returns a function
    # but the mock won't raise. The safe_eel_call wrapper handles the
    # case where eel doesn't have the attribute at all.
    del mock_eel.senderText  # make hasattr return False

    with patch.object(command, "eel", mock_eel), \
         patch.object(command, "speak") as mock_speak, \
         patch.object(command, "_speak_greeting") as mock_greet:
        # "hello" routes to greeting, never touches chatBot/brain.
        try:
            command.allCommands("hello")
        except AttributeError:
            pytest.fail("allCommands raised AttributeError on missing eel function")
        mock_greet.assert_called_once()


def test_safe_eel_call_missing_function_is_noop():
    """safe_eel_call with a non-existent function name must not raise."""
    import engine.command as command

    mock_eel = MagicMock()
    del mock_eel.nonExistentFunc

    with patch.object(command, "eel", mock_eel):
        # Must not raise.
        command.safe_eel_call("nonExistentFunc", "arg1", "arg2")


# ---------------------------------------------------------------------------
# Bridge queue integration: pipeline posts to queue when one is provided
# ---------------------------------------------------------------------------

def test_pipeline_posts_to_bridge_queue_when_queue_present():
    """When a bridge queue is provided, emit_command must put the
    transcript in the queue, not call allCommands directly."""
    import multiprocessing
    q = multiprocessing.Queue()

    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0]),
        command_queue=q,
        asr=lambda a, s: "what is 2+2",
    )
    pipeline.emit_command(b"\x00\x00" * 1600, source="hotword")
    events = [q.get(timeout=1), q.get(timeout=1), q.get(timeout=1)]
    event = next(event for event in events if event["type"] == "command_text")
    assert event["type"] == "command_text"
    assert event["text"] == "what is 2+2"
    assert event["source"] == "hotword"


def test_hotword_posts_wake_and_listening_status():
    import multiprocessing
    q = multiprocessing.Queue()
    pipeline = _fresh_pipeline(command_queue=q)
    pipeline._post_status("wake_detected", source="hotword")
    pipeline._post_status("listening_started", source="hotword")
    events = [q.get(timeout=1), q.get(timeout=1)]
    assert [(event["status"], event["source"]) for event in events] == [
        ("wake_detected", "hotword"),
        ("listening_started", "hotword"),
    ]


def test_clap_posts_wake_and_listening_status():
    import multiprocessing
    q = multiprocessing.Queue()
    pipeline = _fresh_pipeline(command_queue=q)
    pipeline._post_status("wake_detected", source="double_clap")
    pipeline._post_status("listening_started", source="double_clap")
    events = [q.get(timeout=1), q.get(timeout=1)]
    assert [(event["status"], event["source"]) for event in events] == [
        ("wake_detected", "double_clap"),
        ("listening_started", "double_clap"),
    ]


def test_asr_result_posts_transcript_preview():
    import multiprocessing
    q = multiprocessing.Queue()
    pipeline = _fresh_pipeline(
        command_queue=q,
        asr=lambda a, s: "hello from nexi",
    )
    pipeline.emit_command(b"\x00\x00" * 1600, source="hotword")
    events = [q.get(timeout=1), q.get(timeout=1), q.get(timeout=1)]
    asr_result = next(event for event in events if event.get("status") == "asr_result")
    assert asr_result["text"] == "hello from nexi"


def test_pipeline_never_calls_allCommands_directly_when_queue_present():
    """With a bridge queue, allCommands must not be called in this process."""
    import multiprocessing
    q = multiprocessing.Queue()

    pipeline = _fresh_pipeline(
        wake_scorer=ScriptedScorer([0.0]),
        command_queue=q,
        asr=lambda a, s: "hello",
    )
    with patch("engine.command.allCommands") as mock_all:
        pipeline.emit_command(b"\x00\x00" * 1600, source="clap")
        mock_all.assert_not_called()
    events = [q.get(timeout=1), q.get(timeout=1), q.get(timeout=1)]
    assert any(event["type"] == "command_text" and event["source"] == "clap" for event in events)


def test_audio_process_does_not_call_allCommands_when_queue_present():
    test_pipeline_never_calls_allCommands_directly_when_queue_present()


def test_audio_process_does_not_call_eel():
    import multiprocessing
    q = multiprocessing.Queue()
    pipeline = _fresh_pipeline(
        command_queue=q,
        asr=lambda a, s: "hello",
    )
    with patch("eel.DisplayMessage", create=True) as mock_display:
        pipeline.emit_command(b"\x00\x00" * 1600, source="hotword")
        mock_display.assert_not_called()


def test_asr_called_once_per_wake():
    test_asr_called_once_per_emit()


def test_hotword_uses_internal_wake_not_win_j():
    import multiprocessing
    q = multiprocessing.Queue()
    pipeline = _fresh_pipeline(
        command_queue=q,
        asr=lambda a, s: "hello",
    )
    with patch("engine.nexi_wake_controller.wake_nexi") as mock_wake, \
         patch("pyautogui.hotkey") as mock_hotkey:
        pipeline.trigger_wake("hotword")
    mock_wake.assert_called_once_with("hotword")
    mock_hotkey.assert_not_called()


def test_clap_uses_internal_wake_not_win_j():
    import multiprocessing
    q = multiprocessing.Queue()
    pipeline = _fresh_pipeline(
        command_queue=q,
        asr=lambda a, s: "hello",
    )
    with patch("engine.nexi_wake_controller.wake_nexi") as mock_wake, \
         patch("pyautogui.hotkey") as mock_hotkey:
        pipeline.trigger_wake("clap")
    mock_wake.assert_called_once_with("double_clap")
    mock_hotkey.assert_not_called()


def test_win_j_pyautogui_not_called_in_internal_mode():
    pipeline = _fresh_pipeline(asr=lambda a, s: "hello")
    with patch("engine.nexi_wake_controller.wake_nexi") as mock_wake, \
         patch("pyautogui.hotkey") as mock_hotkey:
        pipeline.trigger_wake("hotkey")
    mock_wake.assert_called_once_with("hotkey")
    mock_hotkey.assert_not_called()


def test_pipeline_fallback_calls_allCommands_when_no_queue():
    """When no on_command_text callback is provided, the default handler
    is used. (In tests, the default handler logs a warning and tries
    allCommands — we mock allCommands to verify the fallback.)"""
    from engine.audio_wake_pipeline import AudioWakePipeline
    pipeline = AudioWakePipeline(
        on_command_text=None,  # default handler
        asr=lambda a, s: "open chrome",
        clock=FakeClock(),
    )
    with patch("engine.command.allCommands") as mock_all:
        pipeline.emit_command(b"\x00\x00" * 1600)
        mock_all.assert_called_once_with("open chrome")


def test_successful_wake_with_queue_keeps_session_active_until_bridge_finishes():
    """Regression: on a successful voice command, trigger_wake must NOT finish
    the session itself when an async command queue is present. The bridge owns
    the rest of the lifecycle and resumes detectors only after TTS completes.
    This prevents the mic re-listening while Nexi is recognising/thinking/speaking.
    """
    import multiprocessing
    from engine.wake_session_manager import get_session_manager

    q = multiprocessing.Queue()
    pipeline = _fresh_pipeline(command_queue=q, asr=lambda a, s: "what is the time")

    # Capture returns valid speech audio; emit_command dispatches to the queue
    # (async) and returns the transcript without speaking inline.
    valid_audio = b"\x01\x01" * 30000  # well above ASR_MIN_AUDIO_MS byte gate
    with patch("engine.nexi_wake_controller.wake_nexi"), \
         patch.object(pipeline, "capture_command", return_value=valid_audio), \
         patch.object(pipeline, "emit_command", return_value="what is the time"):
        pipeline._last_capture_stats = {"speech_started": True, "duration_ms": 3000, "speech_ms": 1500}
        result = pipeline.trigger_wake("hotword")

    assert result is True
    # Session must still be active and detectors still paused — the bridge has
    # not finished it yet (TTS hasn't completed in this test).
    mgr = get_session_manager()
    assert mgr.is_active() is True, "session was finished prematurely — mic would re-listen during thinking/speaking"
    assert mgr.are_detectors_paused() is True, "detectors resumed before TTS completed"


def test_no_speech_timeout_finishes_session():
    """Failure path still finishes the session and resumes detectors."""
    from engine.wake_session_manager import get_session_manager

    pipeline = _fresh_pipeline(asr=lambda a, s: "")
    with patch("engine.nexi_wake_controller.wake_nexi"), \
         patch.object(pipeline, "capture_command", return_value=b"\x00\x00" * 10):
        pipeline._last_capture_stats = {"speech_started": False, "duration_ms": 100, "speech_ms": 0}
        result = pipeline.trigger_wake("hotword")

    assert result is False
    assert get_session_manager().is_active() is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
