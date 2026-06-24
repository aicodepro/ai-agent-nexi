import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_tuned_dsp_rejects_silence(monkeypatch):
    monkeypatch.setenv("JARVIS_DSP_CLAP_RMS_THRESHOLD", "0.045")
    monkeypatch.setenv("JARVIS_DSP_CLAP_PEAK_THRESHOLD", "0.14")
    monkeypatch.setenv("JARVIS_DSP_CLAP_PEAK_RATIO", "5.2")
    monkeypatch.setenv("JARVIS_DSP_CLAP_HF_RATIO", "0.43")
    from engine.dsp_clap_backend import DspClapBackend
    result = DspClapBackend().process_pcm16(b"\x00\x00" * 1280)
    assert result.is_clap is False
    assert result.reason.startswith("low_rms")
