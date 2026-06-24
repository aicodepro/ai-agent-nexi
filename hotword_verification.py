#!/usr/bin/env python3
"""
Simple verification that hotword fix has been applied correctly.
"""
import os
from pathlib import Path

def main():
    print("=== HOTWORD FIX VERIFICATION ===\n")
    
    all_good = True
    
    # Check .env.example
    env_path = Path("E:\\jarvis-main\\.env.example")
    if env_path.exists():
        env_content = env_path.read_text()
        if "JARVIS_HOTWORD_MIN_RMS=0.010" in env_content:
            print("✓ .env.example has JARVIS_HOTWORD_MIN_RMS=0.010")
        else:
            print("✗ .env.example missing JARVIS_HOTWORD_MIN_RMS=0.010")
            all_good = False
    else:
        print("✗ .env.example not found")
        all_good = False
    
    # Check audio_wake_pipeline.py
    pipeline_path = Path("engine/audio_wake_pipeline.py")
    if pipeline_path.exists():
        pipeline_content = pipeline_path.read_text()
        if 'HOTWORD_MIN_RMS = _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010)' in pipeline_content:
            print("✓ audio_wake_pipeline.py has correct HOTWORD_MIN_RMS")
        else:
            print("✗ audio_wake_pipeline.py missing correct HOTWORD_MIN_RMS")
            all_good = False
            
        if 'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)' in pipeline_content:
            print("✓ audio_wake_pipeline.py has correct OWW_THRESHOLD")
        else:
            print("✗ audio_wake_pipeline.py missing correct OWW_THRESHOLD")
            all_good = False
            
        if 'OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2)' in pipeline_content:
            print("✓ audio_wake_pipeline.py has correct OWW_CONSECUTIVE")
        else:
            print("✗ audio_wake_pipeline.py missing correct OWW_CONSECUTIVE")
            all_good = False
            
        if 'HOTWORD_RISING_EDGE_DELTA = _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03)' in pipeline_content:
            print("✓ audio_wake_pipeline.py has correct HOTWORD_RISING_EDGE_DELTA")
        else:
            print("✗ audio_wake_pipeline.py missing correct HOTWORD_RISING_EDGE_DELTA")
            all_good = False
    else:
        print("✗ audio_wake_pipeline.py not found")
        all_good = False
    
    # Check hotword_engine_manager.py
    manager_path = Path("engine/hotword_engine_manager.py")
    if manager_path.exists():
        manager_content = manager_path.read_text()
        # Look for the exact pattern in __init__ method
        if 'self.min_rms = float(self.config.get("min_rms", _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010))))' in manager_content:
            print("✓ hotword_engine_manager.py has correct min_rms default")
        else:
            print("✗ hotword_engine_manager.py missing correct min_rms default")
            all_good = False
            
        if 'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03))))' in manager_content:
            print("✓ hotword_engine_manager.py has correct rising_edge_delta default")
        else:
            print("✗ hotword_engine_manager.py missing correct rising_edge_delta default")
            all_good = False
            
        if 'self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35))))' in manager_content:
            print("✓ hotword_engine_manager.py has correct threshold default")
        else:
            print("✗ hotword_engine_manager.py missing correct threshold default")
            all_good = False
            
        if 'self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2))))' in manager_content:
            print("✓ hotword_engine_manager.py has correct consecutive_hits_required default")
        else:
            print("✗ hotword_engine_manager.py missing correct consecutive_hits_required default")
            all_good = False
    else:
        print("✗ hotword_engine_manager.py not found")
        all_good = False
    
    # Check diagnostics.py
    diagnostics_path = Path("engine/diagnostics.py")
    if diagnostics_path.exists():
        diagnostics_content = diagnostics_path.read_text()
        if 'os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.35")' in diagnostics_content:
            print("✓ diagnostics.py has correct OPENWAKEWORD_SCORE_THRESHOLD")
        else:
            print("✗ diagnostics.py missing correct OPENWAKEWORD_SCORE_THRESHOLD")
            all_good = False
    else:
        print("✗ diagnostics.py not found")
        all_good = False
    
    print("\n=== VERIFICATION COMPLETE ===")
    if all_good:
        print("SUCCESS: All hotword fixes have been applied correctly!")
        print("\nKey improvements:")
        print("- Increased JARVIS_HOTWORD_MIN_RMS from 0.003 to 0.010 (better noise rejection)")
        print("- Increased OPENWAKEWORD_SCORE_THRESHOLD from 0.25 to 0.35 (better accuracy)")
        print("- Increased OPENWAKEWORD_CONSECUTIVE_HITS from 1 to 2 (more reliable detection)")
        print("- Increased HOTWORD_RISING_EDGE_DELTA from 0.02 to 0.03 (better signal discrimination)")
        print("- Added JARVIS_HOTWORD_DEBUG=true for troubleshooting")
        return True
    else:
        print("FAILURE: Some hotword fixes were not applied correctly.")
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
