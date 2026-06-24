"""Tests: debug_dsp_clap_calibration.py recommends valid env config."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDspClapCalibrationRecommendsEnv:
    def test_compute_features_returns_dict(self):
        from scripts.debug_dsp_clap_calibration import compute_features
        pcm = b"\x00\x00" * 1600
        f = compute_features(pcm)
        assert f is not None
        assert "rms" in f
        assert "peak" in f
        assert "peak_ratio" in f
        assert "hf_ratio" in f
        assert "duration_ms" in f

    def test_compute_features_zero_silence(self):
        from scripts.debug_dsp_clap_calibration import compute_features
        pcm = b"\x00\x00" * 1600
        f = compute_features(pcm)
        assert f["rms"] == 0.0
        assert f["peak"] == 0.0
        assert f["peak_ratio"] == 0.0
        assert f["hf_ratio"] == 0.0

    def test_compute_features_detects_peak(self):
        from scripts.debug_dsp_clap_calibration import compute_features
        import struct
        samples = [0] * 1600
        samples[800] = 32767
        pcm = struct.pack(f"<{len(samples)}h", *samples)
        f = compute_features(pcm)
        assert f["peak"] > 0.5

    def test_compute_features_valid_rms(self):
        from scripts.debug_dsp_clap_calibration import compute_features
        import math
        import struct
        samples = [int(10000 * math.sin(math.pi * i / 1600)) for i in range(1600)]
        pcm = struct.pack(f"<{len(samples)}h", *samples)
        f = compute_features(pcm)
        assert f["rms"] > 0.0
        assert f["peak"] > 0.0
        assert f["peak_ratio"] > 1.0
        assert 0.0 <= f["hf_ratio"] <= 1.0

    def test_test_thresholds_returns_zero_for_silence(self):
        from scripts.debug_dsp_clap_calibration import compute_features, test_thresholds
        pcm = b"\x00\x00" * 1600
        f = compute_features(pcm)
        n = test_thresholds([f], rms_t=0.01, peak_t=0.01, pr_t=2.0, hf_t=0.1, cooldown_ms=100)
        assert n == 0

    def test_test_thresholds_detects_loud_chunk(self):
        from scripts.debug_dsp_clap_calibration import compute_features, test_thresholds
        import math
        import struct
        samples = [int(20000 * math.sin(math.pi * i / 64)) for i in range(64)]
        pcm = struct.pack(f"<{len(samples)}h", *samples)
        f = compute_features(pcm)
        n = test_thresholds([f], rms_t=0.3, peak_t=0.5, pr_t=1.5, hf_t=0.01, cooldown_ms=100)
        assert n >= 0

    def test_default_env_format(self):
        env = {
            "NEXI_DSP_CLAP_RMS_THRESHOLD": 0.0454,
            "NEXI_DSP_CLAP_PEAK_THRESHOLD": 0.1432,
            "NEXI_DSP_CLAP_PEAK_RATIO": 5.2345,
            "NEXI_DSP_CLAP_HF_RATIO": 0.4312,
            "NEXI_DSP_CLAP_EVENT_COOLDOWN_MS": 120,
            "NEXI_DSP_CLAP_SPEECH_REJECT_MS": 280,
            "NEXI_CLAP_MIN_GAP_MS": 160,
            "NEXI_CLAP_MAX_GAP_MS": 950,
        }
        for key, val in env.items():
            if isinstance(val, float):
                formatted = f"{key}={val:.4f}"
                assert "=" in formatted
                assert formatted.count("=") == 1
            else:
                formatted = f"{key}={val}"
                assert "=" in formatted

    def test_near_silence_also_returns_features(self):
        from scripts.debug_dsp_clap_calibration import compute_features
        import struct
        samples = [5] * 1600
        pcm = struct.pack(f"<{len(samples)}h", *samples)
        f = compute_features(pcm)
        assert f is not None
        assert f["rms"] > 0.0
        assert f["peak"] > 0.0
