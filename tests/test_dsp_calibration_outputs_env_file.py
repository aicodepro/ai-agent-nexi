import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_calibration_writes_env_and_summary(tmp_path, monkeypatch):
    import scripts.debug_dsp_clap_calibration as cal
    monkeypatch.setattr(cal, "ARTIFACTS_DIR", str(tmp_path))
    recommended = {
        "NEXI_DSP_CLAP_RMS_THRESHOLD": 0.045,
        "NEXI_DSP_CLAP_PEAK_THRESHOLD": 0.14,
        "NEXI_DSP_CLAP_PEAK_RATIO": 5.2,
        "NEXI_DSP_CLAP_HF_RATIO": 0.43,
        "NEXI_DSP_CLAP_EVENT_COOLDOWN_MS": 120,
        "NEXI_DSP_CLAP_SPEECH_REJECT_MS": 280,
        "NEXI_CLAP_MIN_GAP_MS": 160,
        "NEXI_CLAP_MAX_GAP_MS": 950,
    }
    paths = cal.write_calibration_artifacts(recommended, {"passes": 4})
    assert os.path.exists(paths["env_path"])
    assert os.path.exists(paths["json_path"])
    assert "$env:NEXI_DSP_CLAP_RMS_THRESHOLD" in open(paths["env_path"], encoding="utf-8").read()
