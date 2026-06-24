"""Test that sounddevice can open the mic stream at pipeline settings."""
import os
import sys
import time

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

import sounddevice as sd
import numpy as np

AUDIO_INPUT_DEVICE = os.getenv("AUDIO_INPUT_DEVICE", "")

device = None
if AUDIO_INPUT_DEVICE:
    device = int(AUDIO_INPUT_DEVICE) if AUDIO_INPUT_DEVICE.isdigit() else AUDIO_INPUT_DEVICE

dev_info = sd.query_devices(device, "input") if device is not None else sd.query_devices(kind="input")
print(f"Pipeline would use device: {dev_info['name']} (idx={dev_info['index']}, ch_in={dev_info['max_input_channels']})")

SAMPLE_RATE = 16000
CHANNELS = 1
FRAME_SAMPLES = 1280

print(f"Opening stream: rate={SAMPLE_RATE} ch={CHANNELS} blocksize={FRAME_SAMPLES}")
try:
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        blocksize=FRAME_SAMPLES,
        dtype="float32",
    )
    stream.start()
    print("Stream started OK")

    # Read a few frames
    for i in range(10):
        data, overflowed = stream.read(FRAME_SAMPLES)
        rms = float(np.sqrt(np.mean(data ** 2)))
        if i == 0:
            print(f"Frame 0: RMS={rms:.6f} overflow={overflowed}")
    print(f"Stream producing audio: RMS={rms:.6f}")

    stream.stop()
    stream.close()
    print("Stream closed OK")
    print("\nPASS: Microphone stream works at pipeline settings.")
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}")
    sys.exit(1)