#!/usr/bin/env python3
"""
Quick test to verify hotword fix.
"""
import sys

def test_hotword_fix():
    print("Testing hotword configuration fix...")
    
    # Check key files
    files_to_check = [
        ("engine/audio_wake_pipeline.py", [
            'HOTWORD_MIN_RMS = _env_float("NEXI_HOTWORD_MIN_RMS", 0.010)',
            'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)',
            'OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2)',
            'HOTWORD_RISING_EDGE_DELTA = _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.03)'
        ]),
        ("engine/hotword_engine_manager.py", [
            'self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35))))',
            'self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2))))',
            'self.min_rms = float(self.config.get("min_rms", _env_float("NEXI_HOTWORD_MIN_RMS", 0.010))))',
            'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.03))))'
        ])
    ]
    
    all_pass = True
    for filename, patterns in files_to_check:
        filepath = f"E:/nexi-main/{filename}"
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                content = f.read()
                for pattern in patterns:
                    if pattern in content:
                        print(f"  ✓ Found correct pattern in {filename}")
                    else:
                        print(f"  ✗ Missing correct pattern in {filename}: {pattern[:50]}...")
                        all_pass = False
        else:
            print(f"  ✗ File not found: {filename}")
            all_pass = False
    
    if all_pass:
        print("
✓ All hotword fixes have been successfully applied!")
        print("
Summary of changes:")
        print("1. Increased NEXI_HOTWORD_MIN_RMS from 0.003 to 0.010")
        print("2. Increased OPENWAKEWORD_SCORE_THRESHOLD from 0.25 to 0.35")
        print("3. Increased OPENWAKEWORD_CONSECUTIVE_HITS from 1 to 2")
        print("4. Increased HOTWORD_RISING_EDGE_DELTA from 0.02 to 0.03")
        print("5. Added NEXI_HOTWORD_DEBUG=true for troubleshooting")
        return True
    else:
        print("
✗ Some fixes were not applied correctly.")
        return False

if __name__ == "__main__":
    import os
    os.chdir("E:/nexi-main")
    success = test_hotword_fix()
    sys.exit(0 if success else 1)
