import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import math
import struct
import unittest
from unittest.mock import patch, MagicMock


def _make_frame(samples):
    return struct.pack("<{}h".format(len(samples)), *samples)


def _make_clap_frame(amplitude=30000):
    samples = [0] * 512 + [amplitude] * 128 + [0] * 384
    return _make_frame(samples)


def _make_silent_frame():
    return _make_frame([0] * 1024)


def _make_noise_frame(rms_scale=3000):
    import random
    samples = [int(random.gauss(0, rms_scale)) for _ in range(1024)]
    for i in range(1024):
        if samples[i] > 32767:
            samples[i] = 32767
        elif samples[i] < -32768:
            samples[i] = -32768
    return _make_frame(samples)


class TestClapDetectorSignal(unittest.TestCase):

    def test_is_clap_frame_returns_true_for_loud_frame(self):
        from engine.clap_detector import is_clap_frame
        frame = _make_clap_frame(30000)
        self.assertTrue(is_clap_frame(frame))

    def test_is_clap_frame_returns_false_for_silence(self):
        from engine.clap_detector import is_clap_frame
        self.assertFalse(is_clap_frame(_make_silent_frame()))

    def test_is_clap_frame_returns_false_for_quiet_noise(self):
        from engine.clap_detector import is_clap_frame
        frame = _make_noise_frame(rms_scale=500)
        self.assertFalse(is_clap_frame(frame))

    def test_detect_double_clap_rejects_single(self):
        from engine.clap_detector import detect_double_clap
        now = time.time()
        self.assertFalse(detect_double_clap([now - 0.5], now))

    def test_detect_double_clap_accepts_two_close(self):
        from engine.clap_detector import detect_double_clap
        now = time.time()
        self.assertTrue(detect_double_clap([now - 0.4, now], now))

    def test_detect_double_clap_rejects_two_too_far(self):
        from engine.clap_detector import detect_double_clap
        now = time.time()
        self.assertFalse(detect_double_clap([now - 5.0, now], now))

    def test_detect_double_clap_rejects_two_too_close(self):
        from engine.clap_detector import detect_double_clap
        now = time.time()
        self.assertFalse(detect_double_clap([now - 0.05, now], now))

    def test_detect_double_clap_uses_third_event_fallback(self):
        from engine.clap_detector import detect_double_clap
        now = time.time()
        events = [now - 0.8, now - 0.35, now]
        self.assertTrue(detect_double_clap(events, now))


class TestClapDetectorIntegration(unittest.TestCase):

    def test_clap_disabled_by_default(self):
        # Reload after clearing env so the module-level constant is
        # re-evaluated. Without the reload this test is order-dependent
        # (any earlier import with CLAP_DETECTION_ENABLED set in .env
        # locks the constant in True).
        with patch.dict(os.environ, {}, clear=True):
            from importlib import reload
            import engine.clap_detector as cd
            reload(cd)
            self.assertFalse(cd.CLAP_DETECTION_ENABLED)

    def test_clap_enabled_when_env_set(self):
        os.environ.pop("DISABLE_CLAP_DETECTION", None)
        with patch.dict(os.environ, {"CLAP_DETECTION_ENABLED": "true"}, clear=True):
            from importlib import reload
            import engine.clap_detector as cd
            reload(cd)
            self.assertTrue(cd.CLAP_DETECTION_ENABLED)

    def test_single_clap_does_not_wake_in_double_mode(self):
        from engine.clap_detector import detect_double_clap
        now = time.time()
        self.assertFalse(detect_double_clap([now - 0.3], now))
        self.assertFalse(detect_double_clap([now - 0.7], now))

    def test_double_clap_wakes(self):
        from engine.clap_detector import detect_double_clap
        now = time.time()
        self.assertTrue(detect_double_clap([now - 0.3, now], now))

    def test_missing_model_does_not_crash(self):
        from engine.clap_detector import ClapListener
        listener = ClapListener()
        self.assertIsNotNone(listener)
        listener.stop()

    def test_callback_is_none_by_default(self):
        from engine.clap_detector import ClapListener
        listener = ClapListener()
        self.assertIsNone(listener._on_wake_callback)

    def test_low_rms_noise_rejected(self):
        from engine.clap_detector import is_clap_frame
        frame = _make_noise_frame(rms_scale=200)
        self.assertFalse(is_clap_frame(frame))

    def test_peak_without_second_clap_rejected(self):
        from engine.clap_detector import detect_double_clap
        now = time.time()
        self.assertFalse(detect_double_clap([now - 0.3], now))


class TestClapDetectorCooldown(unittest.TestCase):

    def test_cooldown_blocks_repeat_wake(self):
        from engine.clap_detector import ClapListener, detect_double_clap
        import engine.clap_detector as cd
        orig_cooldown = cd.CLAP_COOLDOWN_SECONDS
        cd.CLAP_COOLDOWN_SECONDS = 5.0
        try:
            listener = ClapListener()
            now = time.time()
            listener._last_wake_at = now
            self.assertAlmostEqual(listener._last_wake_at, now, delta=0.01)
        finally:
            cd.CLAP_COOLDOWN_SECONDS = orig_cooldown


# ---------------------------------------------------------------------------
# CLAP_NN source-integration tests (Option A / B / C selection)
# ---------------------------------------------------------------------------

class TestClapNNSourceStrategy(unittest.TestCase):

    def test_select_strategy_returns_rms_when_no_model(self):
        """No CLAP_MODEL_PATH set -> RMS fallback."""
        from engine.clap_detector import select_strategy
        with patch.dict(os.environ, {"CLAP_MODEL_PATH": ""}, clear=False):
            self.assertEqual(select_strategy(), "rms_signal")

    def test_select_strategy_returns_rms_when_model_path_invalid(self):
        from engine.clap_detector import select_strategy
        with patch.dict(os.environ, {"CLAP_MODEL_PATH": "Z:/does/not/exist.pth"}, clear=False):
            self.assertEqual(select_strategy(), "rms_signal")

    def test_clap_source_strategy_selected(self):
        """Listener picks a strategy at start() and logs it. With no model
        path, the strategy must be 'rms_signal' and the listener must not
        crash."""
        from engine.clap_detector import ClapListener
        listener = ClapListener()
        listener._init_strategy()
        self.assertEqual(listener._strategy, "rms_signal")
        self.assertIsNone(listener._model_detector)

    def test_clap_source_adapter_if_model_available(self):
        """When the adapter reports a usable model, the listener wires
        it in and switches strategy to 'clap_nn_model'. We mock the
        adapter so we don't need torch or a real .pth."""
        from engine.clap_detector import ClapListener

        fake_detector = MagicMock()
        fake_detector.predict_pcm16.return_value = (True, 0.999)

        with patch("engine.clap_model_adapter.try_load_model_detector",
                   return_value=fake_detector):
            listener = ClapListener()
            listener._init_strategy()
            self.assertEqual(listener._strategy, "clap_nn_model")
            self.assertIs(listener._model_detector, fake_detector)

            # Per-frame decision is delegated to the model.
            self.assertTrue(listener._is_clap(b"\x00" * 32))
            fake_detector.predict_pcm16.assert_called()

    def test_signal_fallback_only_after_source_audit(self):
        """The RMS fallback is engaged only when the adapter declines.
        This proves Option C is never taken silently — the adapter must
        be consulted first."""
        from engine.clap_detector import ClapListener

        with patch("engine.clap_model_adapter.try_load_model_detector",
                   return_value=None) as mock_try:
            listener = ClapListener()
            listener._init_strategy()
            mock_try.assert_called_once()
            self.assertEqual(listener._strategy, "rms_signal")

    def test_model_predict_exception_falls_back_per_frame(self):
        """A model exception mid-stream must not crash the listener.
        That frame falls back to RMS; the listener stays alive."""
        from engine.clap_detector import ClapListener

        flaky = MagicMock()
        flaky.predict_pcm16.side_effect = RuntimeError("boom")

        listener = ClapListener()
        listener._model_detector = flaky
        listener._strategy = "clap_nn_model"

        # Loud frame -> RMS would say True. Model raises -> fall back -> True.
        loud = _make_clap_frame(30000)
        self.assertTrue(listener._is_clap(loud))
        flaky.predict_pcm16.assert_called()

    def test_model_unavailable_does_not_crash_listener_construction(self):
        """ClapListener() must construct even when nothing CLAP_NN-related
        is configured. This is the 'missing model does not crash Jarvis'
        guarantee."""
        from engine.clap_detector import ClapListener
        with patch.dict(os.environ, {"CLAP_MODEL_PATH": "/nope.pth"}, clear=False):
            listener = ClapListener()
            self.assertIsNotNone(listener)


# ---------------------------------------------------------------------------
# Adapter unit tests (do not require torch)
# ---------------------------------------------------------------------------

class TestClapModelAdapter(unittest.TestCase):

    def test_is_model_available_false_when_path_unset(self):
        from engine.clap_model_adapter import is_model_available
        with patch.dict(os.environ, {"CLAP_MODEL_PATH": ""}, clear=False):
            self.assertFalse(is_model_available())

    def test_is_model_available_false_when_path_missing(self):
        from engine.clap_model_adapter import is_model_available
        with patch.dict(os.environ, {"CLAP_MODEL_PATH": "Z:/missing.pth"}, clear=False):
            self.assertFalse(is_model_available())

    def test_try_load_model_detector_returns_none_when_unavailable(self):
        from engine.clap_model_adapter import try_load_model_detector
        with patch.dict(os.environ, {"CLAP_MODEL_PATH": ""}, clear=False):
            self.assertIsNone(try_load_model_detector())

    def test_constructor_raises_clap_unavailable_when_path_unset(self):
        from engine.clap_model_adapter import ClapModelDetector, CLAPModelUnavailable
        with patch.dict(os.environ, {"CLAP_MODEL_PATH": ""}, clear=False):
            with self.assertRaises(CLAPModelUnavailable):
                ClapModelDetector()


if __name__ == "__main__":
    unittest.main()
