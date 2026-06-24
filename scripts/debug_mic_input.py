"""Debug JARVIS microphone input. Lists devices, records 3s, computes RMS.

Usage: python scripts/debug_mic_input.py
"""

import os
import sys
import time
import struct

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

print("=== JARVIS Microphone Input Debug ===")
print()

# 1. List all audio devices via pyaudio
print("[1] Audio devices (PyAudio)")
print("-" * 60)
try:
    import pyaudio
    pa = pyaudio.PyAudio()
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        kind = "INPUT " if int(info.get("maxInputChannels", 0)) > 0 else "OUTPUT"
        host_api = pa.get_host_api_info_by_index(int(info.get("hostApi", 0)))
        name = info.get("name", "unknown")
        rate = int(info.get("defaultSampleRate", 0))
        ch_in = int(info.get("maxInputChannels", 0))
        print(f"  [{i:2d}] {kind} | {name[:60]:60s} | rate={rate} ch_in={ch_in}")
    pa.terminate()
except ImportError:
    print("  PyAudio not installed")
except Exception as e:
    print(f"  PyAudio error: {e}")

print()

# 2. List devices via sounddevice
print("[2] Audio devices (sounddevice)")
print("-" * 60)
try:
    import sounddevice as sd
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        ch_in = int(dev.get("max_input_channels", 0))
        kind = "INPUT " if ch_in > 0 else "OUTPUT"
        name = dev.get("name", "unknown")
        rate = int(dev.get("default_samplerate", 0))
        print(f"  [{i:2d}] {kind} | {name[:60]:60s} | rate={rate} ch_in={ch_in}")
    # Show default input
    try:
        default_in = sd.query_devices(kind="input")
        print(f"\n  Default INPUT: {default_in.get('name', 'unknown')} (idx={default_in.get('index', '?')})")
    except Exception:
        print("  No default input device found!")
except ImportError:
    print("  sounddevice not installed")
except Exception as e:
    print(f"  sounddevice error: {e}")

print()

# 3. Try to record for 3 seconds via PyAudio
print("[3] Recording test (PyAudio, 3 seconds)")
print("-" * 60)
try:
    import pyaudio
    pa = pyaudio.PyAudio()

    # Find default input device
    default_idx = pa.get_default_input_device_info().get("index", None)
    if default_idx is None:
        print("  FAIL: No default input device!")
        pa.terminate()
        sys.exit(1)
    info = pa.get_device_info_by_index(default_idx)
    print(f"  Device: {info.get('name', 'unknown')}")
    print(f"  Rate: {int(info.get('defaultSampleRate', 16000))}")
    print(f"  Channels: {int(info.get('maxInputChannels', 1))}")
    print()
    print("  Listening for 3 seconds... speak or clap now!")

    stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        input_device_index=default_idx,
        frames_per_buffer=1024,
    )

    frames = []
    start = time.time()
    rms_peaks = []
    while time.time() - start < 3.0:
        try:
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
            # Compute RMS
            n = len(data) // 2
            if n > 0:
                samples = struct.unpack(f"<{n}h", data)
                sum_sq = sum(s * s for s in samples)
                rms = (sum_sq / n) ** 0.5 / 32768.0
                peak = max(abs(s) for s in samples) / 32768.0
                rms_peaks.append((rms, peak))
        except Exception:
            pass

    stream.stop_stream()
    stream.close()
    pa.terminate()

    print(f"  Frames captured: {len(frames)}")
    if rms_peaks:
        rms_values = [r for r, p in rms_peaks]
        peak_values = [p for r, p in rms_peaks]
        avg_rms = sum(rms_values) / len(rms_values)
        max_rms = max(rms_values)
        max_peak = max(peak_values)
        print(f"  Average RMS: {avg_rms:.6f}")
        print(f"  Max RMS: {max_rms:.6f}")
        print(f"  Max Peak: {max_peak:.6f}")

        if max_rms < 0.005:
            print()
            print("  FAIL: Audio signal too quiet — mic may be muted or wrong device.")
            print("  Check Windows mic privacy settings and default input device.")
            sys.exit(1)
        elif max_rms < 0.02:
            print()
            print("  WARN: Low audio levels detected. Hotword/clap may not trigger.")
        else:
            print()
            print("  PASS: Microphone is capturing audio with adequate levels.")
    else:
        print("  FAIL: No audio frames captured.")
        sys.exit(1)

except ImportError:
    print("  PyAudio not installed — cannot test mic.")
    sys.exit(1)
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")
    sys.exit(1)

print()

# 4. Test sounddevice (used by OWW pipeline)
print("[4] Recording test (sounddevice, 1 second)")
print("-" * 60)
try:
    import sounddevice as sd
    import numpy as np

    duration = 1.0
    sample_rate = 16000
    print(f"  Recording {duration}s at {sample_rate}Hz...")
    recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    rms = float(np.sqrt(np.mean(recording ** 2)))
    peak = float(np.max(np.abs(recording)))
    print(f"  RMS: {rms:.6f}  Peak: {peak:.6f}")
    if rms > 0.001:
        print("  PASS: sounddevice is capturing audio.")
    else:
        print("  FAIL: sounddevice captured silence or muted device.")
except ImportError:
    print("  sounddevice not installed.")
except Exception as e:
    print(f"  FAIL: {type(e).__name__}: {e}")

print()
print("=== DONE ===")