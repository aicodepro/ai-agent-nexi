"""
CLAP_NN Backend — real-time clap detection using the trained CNN model.

Loads the AudioClassifier CNN, preprocesses incoming 16 kHz PCM16 audio
into mel spectrograms matching the training pipeline, and returns
per-frame clap probability.

Does NOT save WAV files per inference (in-memory buffer only).
If model file is missing, fails clearly with a readable message.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ClapNNResult:
    is_clap: bool = False
    confidence: float = 0.0
    timestamp: float = 0.0
    rms: float = 0.0
    peak: float = 0.0
    reason: str = ""


class ClapNNBackend:
    """Real-time CLAP_NN clap detection for Nexi 16 kHz pipeline.

    If torch/torchaudio/torchvision are missing or the model file does not
    exist, init fails with a readable message.
    """

    def __init__(
        self,
        model_path: str = "",
        sample_rate: int = 16000,
        threshold: float = 0.85,
        window_ms: int = 600,
        stride_ms: int = 100,
        model_sample_rate: int = 44100,
        n_mels: int = 128,
        n_fft: int = 400,
        hop_length: int = 200,
        target_size: int = 256,
    ):
        self._model_path = model_path
        self._input_sr = int(sample_rate)
        self._model_sr = int(model_sample_rate)
        self._threshold = float(threshold)
        self._window_ms = int(window_ms)
        self._stride_ms = int(stride_ms)
        self._n_mels = int(n_mels)
        self._n_fft = int(n_fft)
        self._hop_length = int(hop_length)
        self._target_size = int(target_size)
        self._name = "clap_nn"
        self._loaded = False
        self._model = None
        self._ready = False
        self._last_error = ""

        # --- streaming state: rolling window + edge-triggered onset gating ---
        # The model classifies a ~600 ms clip, but the pipeline feeds 80 ms frames. So we
        # keep a rolling window of recent audio and only invoke the CNN when a frame carries
        # a clap-like onset (peak >= trigger), then suppress re-fires for a refractory period
        # so one physical clap = one event (the double-clap state machine handles timing).
        self._win_bytes = max(2, int(self._input_sr * self._window_ms / 1000)) * 2
        self._buf = bytearray()
        self._trigger_peak = float(os.getenv("NEXI_CLAP_NN_TRIGGER_PEAK", "0.12"))
        self._refractory_sec = max(0.0, float(os.getenv("NEXI_CLAP_NN_REFRACTORY_MS", "120"))) / 1000.0
        self._threshold = float(os.getenv("NEXI_CLAP_NN_THRESHOLD", str(self._threshold)))
        self._debug = (os.getenv("NEXI_CLAP_DEBUG", "") or "").strip().lower() in {"1", "true", "yes", "on"}
        self._last_fire_ts = -1e9

        if not model_path or not os.path.isfile(model_path):
            self._last_error = f"CLAP_NN model file not found: {model_path}"
            print(f"[CLAP_NN] not_ready reason=model_missing path={model_path}", flush=True)
            return

        try:
            self._load_model(model_path)
        except Exception as e:
            self._last_error = f"CLAP_NN load failed: {type(e).__name__}: {e}"
            print(f"[CLAP_NN] {self._last_error}", flush=True)

    def _load_model(self, model_path: str) -> None:
        """Load the AudioClassifier CNN and its trained weights."""
        import torch

        # Import the model architecture from the extracted source
        import sys
        inspect_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "external", "CLAP_NN_INSPECT", "CLAP_NN")
        if inspect_dir not in sys.path:
            sys.path.insert(0, inspect_dir)

        try:
            from cnn_sound_model import AudioClassifier
        except ImportError:
            # Try alternate import paths
            try:
                sys.path.insert(0, os.path.join(inspect_dir, "CLAP_NN"))
                from cnn_sound_model import AudioClassifier
            except ImportError:
                raise ImportError(
                    "Cannot import cnn_sound_model.py. "
                    "Ensure CLAP_NN source is at external/CLAP_NN_INSPECT/CLAP_NN/"
                )

        self._model = AudioClassifier()
        state_dict = torch.load(model_path, map_location=torch.device("cpu"))
        self._model.load_state_dict(state_dict)
        self._model.eval()
        self._loaded = True
        self._ready = True
        print(f"[CLAP_NN] loaded model={model_path} params={sum(p.numel() for p in self._model.parameters())}", flush=True)

        # Precompute the mel filterbank for the model's sample rate
        self._mel_basis = self._create_mel_filterbank(
            self._model_sr, self._n_fft, self._n_mels
        )

        # Resampling ratio
        self._resample_ratio = self._model_sr / self._input_sr

    def _create_mel_filterbank(self, sr: int, n_fft: int, n_mels: int) -> np.ndarray:
        """Create mel filterbank matrix (n_mels × n_fft//2+1)."""
        low_freq_mel = 0.0
        high_freq_mel = 2595.0 * math.log10(1.0 + (sr / 2.0) / 700.0)
        mel_points = np.linspace(low_freq_mel, high_freq_mel, n_mels + 2)
        hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)
        bin = np.floor((n_fft + 1) * hz_points / sr).astype(int)
        bin = np.clip(bin, 0, n_fft // 2)

        fbank = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
        for m in range(1, n_mels + 1):
            f_m_minus = int(bin[m - 1])
            f_m = int(bin[m])
            f_m_plus = int(bin[m + 1])
            for k in range(f_m_minus, f_m):
                fbank[m - 1, k] = (k - bin[m - 1]) / (bin[m] - bin[m - 1])
            for k in range(f_m, f_m_plus):
                fbank[m - 1, k] = (bin[m + 1] - k) / (bin[m + 1] - bin[m])
        return fbank

    def _pcm16_to_mel_spec(self, pcm16: bytes) -> Optional[np.ndarray]:
        """Convert PCM16 bytes to normalized mel spectrogram (1, 256, 256)."""
        import torch

        samples = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0

        if len(samples) < self._n_fft:
            return None

        # Resample if input rate differs from model rate
        if self._input_sr != self._model_sr:
            target_len = int(len(samples) * self._resample_ratio)
            if target_len > 0:
                indices = np.linspace(0, len(samples) - 1, target_len)
                samples = np.interp(indices, np.arange(len(samples)), samples)

        # STFT
        import torch.nn.functional as F
        window = torch.hann_window(self._n_fft)
        samples_t = torch.from_numpy(samples).unsqueeze(0)
        stft = torch.stft(samples_t, n_fft=self._n_fft, hop_length=self._hop_length,
                          win_length=self._n_fft, window=window, return_complex=True)
        mag = stft.abs().numpy().squeeze()

        # Mel filter
        mel_spec = self._mel_basis @ mag
        mel_spec = np.maximum(mel_spec, 1e-10)
        mel_spec = np.log(mel_spec)

        # Resize to 256×256 using torch interpolation
        mel_t = torch.from_numpy(mel_spec).unsqueeze(0).unsqueeze(0)  # (1,1,H,W)
        mel_t = F.interpolate(mel_t, size=(self._target_size, self._target_size),
                              mode="bilinear", align_corners=False)
        mel_spec = mel_t.squeeze().numpy()

        # Normalize
        mean = mel_spec.mean()
        std = mel_spec.std()
        if std > 1e-10:
            mel_spec = (mel_spec - mean) / std
        else:
            mel_spec = mel_spec - mean

        return mel_spec[np.newaxis, :, :]  # (1, 256, 256)

    def _classify_window(self) -> float:
        """Run the CNN on the rolling window (left-padded to the full length) -> clap prob.

        Extracted as a seam so streaming/edge-trigger logic can be unit-tested without a model.
        """
        import torch

        window = self._buf
        if len(window) < self._win_bytes:  # left-pad with silence so it's always a full clip
            window = bytes(self._win_bytes - len(window)) + bytes(window)
        else:
            window = bytes(window[-self._win_bytes:])
        mel = self._pcm16_to_mel_spec(window)
        if mel is None:
            return 0.0
        with torch.no_grad():
            inp = torch.from_numpy(mel).unsqueeze(0).float()  # (1,1,256,256)
            output = self._model(inp)
            probs = torch.exp(output)  # log_softmax -> softmax
            return float(probs[0, 1].item())

    def process_pcm16(self, pcm16: bytes, timestamp: float) -> ClapNNResult:
        """Process a 16 kHz PCM16 frame (rolling-window + edge-triggered) -> clap result."""
        rms, peak = self._calc_rms_peak(pcm16)
        if not self._loaded or not self._ready or self._model is None:
            return ClapNNResult(is_clap=False, timestamp=timestamp, rms=rms, peak=peak,
                                reason=self._last_error or "model_not_loaded")

        # Maintain the rolling window.
        self._buf.extend(pcm16)
        excess = len(self._buf) - self._win_bytes
        if excess > 0:
            del self._buf[:excess]

        def _r(is_clap, conf, reason):
            if self._debug:
                print(f"[CLAP_NN] is_clap={str(is_clap).lower()} conf={conf:.3f} peak={peak:.3f} reason={reason}", flush=True)
            return ClapNNResult(is_clap=is_clap, confidence=conf, timestamp=timestamp,
                                rms=rms, peak=peak, reason=reason)

        # One event per physical clap: ignore frames during the refractory window.
        if timestamp - self._last_fire_ts < self._refractory_sec:
            return _r(False, 0.0, "refractory")

        # Onset gate: only run the CNN when this frame carries a clap-like transient peak.
        if peak < self._trigger_peak:
            return _r(False, 0.0, "below_trigger")

        try:
            clap_prob = self._classify_window()
        except Exception as e:
            return _r(False, 0.0, f"inference_error:{type(e).__name__}")

        if clap_prob >= self._threshold:
            self._last_fire_ts = timestamp
            return _r(True, clap_prob, "clap_detected")
        return _r(False, clap_prob, "onset_not_clap")

    @staticmethod
    def _calc_rms_peak(pcm16: bytes) -> tuple[float, float]:
        try:
            n = len(pcm16) // 2
            if n <= 0:
                return 0.0, 0.0
            import struct
            samples = struct.unpack(f"<{n}h", pcm16)
            sum_sq = 0
            peak = 0
            for s in samples:
                sum_sq += s * s
                abs_s = abs(s)
                if abs_s > peak:
                    peak = abs_s
            return (sum_sq / n) ** 0.5 / 32768.0, peak / 32768.0
        except Exception:
            return 0.0, 0.0

    def reset(self) -> None:
        self._buf.clear()
        self._last_fire_ts = -1e9

    def get_status(self) -> dict:
        return {
            "name": self._name,
            "loaded": self._loaded,
            "ready": self._ready,
            "model_path": self._model_path,
            "threshold": self._threshold,
            "model_sample_rate": self._model_sr,
            "input_sample_rate": self._input_sr,
            "last_error": self._last_error,
        }
