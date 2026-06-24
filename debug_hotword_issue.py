#!/usr/bin/env python3
"""
Debug hotword issue where it detects random noises incorrectly.
"""
import os
import sys
import time
import tempfile
import numpy as np

# Add engine to path
sys.path.insert(0, 'E:\\jarvis-main\\engine')

from audio_wake_pipeline import AudioWakePipeline, build_vad
from hotword_engine_manager import HotwordEngineManager
from openwakeword.model import Model as OwwModel
from openwakeword.utils import download_models

def test_hotword_config():
    """Test current hotword configuration and detect issues"""
    print("=== HOTWORD ISSUE DEBUG ===")
    
    # 1. Check environment variables
    print("\n1. Environment Variables:")
    print(f"   JARVIS_HOTWORD_ENABLED: {os.getenv('JARVIS_HOTWORD_ENABLED', 'NOT_SET')}")
    print(f"   JARVIS_HOTWORD_PHRASES: {os.getenv('JARVIS_HOTWORD_PHRASES', 'NOT_SET')}")
    print(f"   JARVIS_HOTWORD_BACKEND_ORDER: {os.getenv('JARVIS_HOTWORD_BACKEND_ORDER', 'NOT_SET')}")
    print(f"   VOICE_WAKE_BACKEND: {os.getenv('VOICE_WAKE_BACKEND', 'NOT_SET')}")
    print(f"   OPENWAKEWORD_ENABLED: {os.getenv('OPENWAKEWORD_ENABLED', 'NOT_SET')}")
    print(f"   JARVIS_HOTWORD_MIN_RMS: {os.getenv('JARVIS_HOTWORD_MIN_RMS', 'NOT_SET')}")
    print(f"   JARVIS_HOTWORD_RISING_EDGE_DELTA: {os.getenv('JARVIS_HOTWORD_RISING_EDGE_DELTA', 'NOT_SET')}")
    
    # 2. Test HotwordEngineManager directly
    print("\n2. Testing HotwordEngineManager:")
    try:
        hotword_manager = HotwordEngineManager()
        status = hotword_manager.get_status()
        print(f"   Enabled: {status['enabled']}")
        print(f"   Phrase: {status['phrase']}")
        print(f"   Threshold: {status['threshold']}")
        print(f"   Min RMS: {status['min_rms']}")
        print(f"   Rising Edge Delta: {status['rising_edge_delta']}")
        print(f"   Model Name: {status['model_name']}")
        print(f"   Load Error: {status['load_error']}")
        
        # Test with different audio samples
        print("\n3. Testing audio samples:")
        
        # Generate test signals
        sample_rate = status['sample_rate']
        frame_duration_ms = status['frame_ms']
        frame_samples = int(sample_rate * frame_duration_ms / 1000)
        
        # Silent frame
        silent_frame = np.zeros(frame_samples, dtype=np.int16)
        silent_bytes = silent_frame.tobytes()
        
        # Generate a test "clap" sound (short burst of noise)
        clap_samples = int(sample_rate * 50 / 1000)  # 50ms clap
        clap_frame = np.random.randint(-32768, 32767, size=clap_samples, dtype=np.int16)
        clap_bytes = clap_frame.tobytes()
        
        # Generate "hey jarvis" audio sample (simulated)
        # We'll just use a high amplitude noise for testing
        voice_samples = int(sample_rate * 200 / 1000)  # 200ms voice sample
        voice_frame = np.random.randint(-8000, 8000, size=voice_samples, dtype=np.int16)
        voice_bytes = voice_frame.tobytes()
        
        # Test each frame
        test_cases = [
            ("Silent", silent_bytes),
            ("Clap (noise burst)", clap_bytes),
            ("Voice-like (medium energy)", voice_bytes)
        ]
        
        for name, audio_bytes in test_cases:
            try:
                result = hotword_manager.process_audio_chunk(audio_bytes, sample_rate)
                print(f"\n   {name}:")
                print(f"     Detected: {result.detected}")
                print(f"     Score: {result.score:.4f}")
                print(f"     Reason: {result.reason}")
                print(f"     RMS gate: {'PASS' if result.score > 0.5 else 'FAIL'}")
                
                if result.detected:
                    print(f"     *** FALSE POSITIVE DETECTED ***")
                    
            except Exception as e:
                print(f"   {name}: ERROR - {e}")
                
    except Exception as e:
        print(f"Error testing HotwordEngineManager: {e}")
        import traceback
        traceback.print_exc()

def test_pipeline_hotword_path():
    """Test the hotword detection through the AudioWakePipeline"""
    print("\n4. Testing AudioWakePipeline hotword detection:")
    
    try:
        # Create a pipeline with only hotword scorer
        pipeline = AudioWakePipeline()
        
        if pipeline._wake_scorer is None:
            print("   WARNING: No wake scorer available - trying to start pipeline")
            try:
                pipeline.start()
            except Exception as e:
                print(f"   Failed to start pipeline: {e}")
                return
        
        print(f"   Wake scorer type: {type(pipeline._wake_scorer)}")
        print(f"   Is running: {pipeline.is_running}")
        
        # Generate test frames
        sample_rate = 16000
        frame_ms = 80
        frame_samples = int(sample_rate * frame_ms / 1000)
        
        # Test with silent frames
        silent_frame = np.zeros(frame_samples, dtype=np.int16)
        
        # Test with noise
        noise_frame = np.random.randint(-8000, 8000, size=frame_samples, dtype=np.int16)
        
        # Process silent frame
        print("\n   Processing silent frame:")
        result = pipeline.process_frame(silent_frame.tobytes())
        print(f"     Result: {result}")
        
        print("\n   Processing noise frame:")
        result = pipeline.process_frame(noise_frame.tobytes())
        print(f"     Result: {result}")
        
        pipeline.stop()
        
    except Exception as e:
        print(f"Error testing AudioWakePipeline: {e}")
        import traceback
        traceback.print_exc()

def test_openwakeword_directly():
    """Test openWakeWord model directly"""
    print("\n5. Testing openWakeWord model directly:")
    
    try:
        print("   Downloading openWakeWord models...")
        download_models()
        
        # Create model
        models = ["hey jarvis"]
        print(f"   Creating model with phrases: {models}")
        model = OwwModel(wakeword_models=models, inference_framework="onnx")
        
        # Generate test frames
        sample_rate = 16000
        frame_ms = 80
        frame_samples = int(sample_rate * frame_ms / 1000)
        
        # Silent frame
        silent = np.zeros(frame_samples, dtype=np.int16)
        
        # Noise frame
        noise = np.random.randint(-8000, 8000, size=frame_samples, dtype=np.int16)
        
        # Process
        print("\n   Processing silent frame:")
        silent_result = model.predict(silent)
        print(f"     Prediction: {silent_result}")
        
        print("\n   Processing noise frame:")
        noise_result = model.predict(noise)
        print(f"     Prediction: {noise_result}")
        
    except Exception as e:
        print(f"Error testing openWakeWord directly: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Starting hotword issue debug...")
    
    test_hotword_config()
    test_pipeline_hotword_path()
    test_openwakeword_directly()
    
    print("\n=== DEBUG COMPLETE ===")
    print("\nSUMMARY:")
    print("If hotword is detecting random noises, possible causes:")
    print("1. HOTWORD_MIN_RMS threshold too low")
    print("2. Missing or ineffective RMS gate")
    print("3. openWakeWord model too sensitive")
    print("4. Rising edge delta too low")
    print("5. Consecutive hits requirement too low")
    print("6. Missing or incorrect audio preprocessing")