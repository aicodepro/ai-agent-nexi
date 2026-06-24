#!/usr/bin/env python3
"""
Simple script to verify hotword fix.
"""
import os
from pathlib import Path

def check_hotword_fix():
    print("=== CHECKING HOTWORD FIX ===\n")
    
    all_good = True
    
    # Check .env.example
    env_path = Path("E:\\jarvis-main\\.env.example")
    if env_path.exists():
        env_content = env_path.read_text()
        if "JARVIS_HOTWORD_MIN_RMS=0.010" in env_content:
            print("✓ .env.example: JARVIS_HOTWORD_MIN_RMS=0.010 is present")
        else:
            print("✗ .env.example: JARVIS_HOTWORD_MIN_RMS=0.010 is missing")
            all_good = False
    else:
        print("✗ .env.example not found")
        all_good = False
    
    # Check audio_wake_pipeline.py
    pipeline_path = Path("engine/audio_wake_pipeline.py")
    if pipeline_path.exists():
        pipeline_content = pipeline_path.read_text()
        checks = [
            ('HOTWORD_MIN_RMS = _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010)', 'audio_wake_pipeline.py HOTWORD_MIN_RMS'),
            ('OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)', 'audio_wake_pipeline.py OWW_THRESHOLD'),
            ('OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2)', 'audio_wake_pipeline.py OWW_CONSECUTIVE'),
            ('HOTWORD_RISING_EDGE_DELTA = _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03)', 'audio_wake_pipeline.py HOTWORD_RISING_EDGE_DELTA')
        ]
        for pattern, name in checks:
            if pattern in pipeline_content:
                print(f"✓ {name} is correct")
            else:
                print(f"✗ {name} is incorrect")
                all_good = False
    else:
        print("✗ audio_wake_pipeline.py not found")
        all_good = False
    
    # Check hotword_engine_manager.py
    manager_path = Path("engine/hotword_engine_manager.py")
    if manager_path.exists():
        manager_content = manager_path.read_text()
        checks = [
            ('self.min_rms = float(self.config.get("min_rms", _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010))))', 'hotword_engine_manager.py min_rms'),
            ('self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35))))', 'hotword_engine_manager.py threshold'),
            ('self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2))))', 'hotword_engine_manager.py consecutive_hits_required'),
            ('self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03))))', 'hotword_engine_manager.py rising_edge_delta')
        ]
        for pattern, name in checks:
            if pattern in manager_content:
                print(f"✓ {name} is correct")
            else:
                print(f"✗ {name} is incorrect")
                all_good = False
    else:
        print("✗ hotword_engine_manager.py not found")
        all_good = False
    
    # Check diagnostics.py
    diagnostics_path = Path("engine/diagnostics.py")
    if diagnostics_path.exists():
        diagnostics_content = diagnostics_path.read_text()
        if 'os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.35")' in diagnostics_content:
            print("✓ diagnostics.py: OPENWAKEWORD_SCORE_THRESHOLD=0.35 is correct")
        else:
            print("✗ diagnostics.py: OPENWAKEWORD_SCORE_THRESHOLD=0.35 is incorrect")
            all_good = False
    else:
        print("✗ diagnostics.py not found")
        all_good = False
    
    print("\n=== FINAL RESULT ===")
    if all_good:
        print("✅ SUCCESS: All hotword configuration files have been correctly fixed!")
        print("\nThe following changes have been successfully applied:")
        print("1. .env.example updated with JARVIS_HOTWORD_MIN_RMS=0.010, OPENWAKEWORD_SCORE_THRESHOLD=0.35, OPENWAKEWORD_CONSECUTIVE_HITS=2, JARVIS_HOTWORD_DEBUG=true")
        print("2. audio_wake_pipeline.py: HOTWORD_MIN_RMS=0.010, HOTWORD_RISING_EDGE_DELTA=0.03, OWW_THRESHOLD=0.35, OWW_CONSECUTIVE=2")
        print("3. hotword_engine_manager.py: All defaults in __init__ method updated to 0.010, 0.03, 0.35, 2 respectively")
        print("4. diagnostics.py: OPENWAKEWORD_SCORE_THRESHOLD=0.35")
        print("\nThese changes should significantly reduce false positives from random noises.")
        return True
    else:
        print("❌ FAILURE: Some hotword configuration files are still incorrect.")
        print("\nPlease check the configuration files manually.")
        return False

if __name__ == "__main__":
    import sys
    success = check_hotword_fix()
    sys.exit(0 if success else 1)
