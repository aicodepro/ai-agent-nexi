import math
import os
import struct
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def speech_like_frame(total=1280):
    samples = []
    for i in range(total):
        val = 0.08 * math.sin(2 * math.pi * 180 * i / 16000.0) + 0.04 * math.sin(2 * math.pi * 420 * i / 16000.0)
        samples.append(int(val * 32767))
    return struct.pack(f"<{len(samples)}h", *samples)


def test_tuned_dsp_rejects_speech_like_audio(monkeypatch):
    monkeypatch.setenv("NEXI_DSP_CLAP_RMS_THRESHOLD", "0.045")
    monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_THRESHOLD", "0.14")
    monkeypatch.setenv("NEXI_DSP_CLAP_PEAK_RATIO", "5.2")
    monkeypatch.setenv("NEXI_DSP_CLAP_HF_RATIO", "0.43")
    from engine.dsp_clap_backend import DspClapBackend
    dsp = DspClapBackend()
    result = dsp.process_pcm16(speech_like_frame())
    assert result.is_clap is False
