#!/usr/bin/env python3
"""
Simple verification that hotword configuration fixes have been applied.
"""
import os
from pathlib import Path

def verify_hotword_fix():
    print("=== VERIFYING HOTWORD CONFIGURATION FIXES ===\n")
    
    all_good = True
    
    # 1. Check .env.example
    print("1. Checking .env.example...")
    env_path = Path("E:\\nexi-main\\.env.example")
    if env_path.exists():
        env_content = env_path.read_text()
        
        if "NEXI_HOTWORD_MIN_RMS=0.010" in env_content:
            print("   ✓ NEXI_HOTWORD_MIN_RMS=0.010 is present")
        else:
            print("   ✗ NEXI_HOTWORD_MIN_RMS=0.010 is missing")
            all_good = False
            
        if "OPENWAKEWORD_SCORE_THRESHOLD=0.35" in env_content:
            print("   ✓ OPENWAKEWORD_SCORE_THRESHOLD=0.35 is present")
        else:
            print("   ✗ OPENWAKEWORD_SCORE_THRESHOLD=0.35 is missing")
            all_good = False
            
        if "OPENWAKEWORD_CONSECUTIVE_HITS=2" in env_content:
            print("   ✓ OPENWAKEWORD_CONSECUTIVE_HITS=2 is present")
        else:
            print("   ✗ OPENWAKEWORD_CONSECUTIVE_HITS=2 is missing")
            all_good = False
            
        if "NEXI_HOTWORD_DEBUG=true" in env_content:
            print("   ✓ NEXI_HOTWORD_DEBUG=true is present")
        else:
            print("   ✗ NEXI_HOTWORD_DEBUG=true is missing")
            all_good = False
    else:
        print("   ✗ .env.example not found")
        all_good = False
    
    # 2. Check audio_wake_pipeline.py
    print("\n2. Checking audio_wake_pipeline.py...")
    pipeline_path = Path("engine/audio_wake_pipeline.py")
    if pipeline_path.exists():
        pipeline_content = pipeline_path.read_text()
        
        if 'HOTWORD_MIN_RMS = _env_float("NEXI_HOTWORD_MIN_RMS", 0.010)' in pipeline_content:
            print("   ✓ audio_wake_pipeline.py: HOTWORD_MIN_RMS=0.010")
        else:
            print("   ✗ audio_wake_pipeline.py: HOTWORD_MIN_RMS missing")
            all_good = False
            
        if 'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)' in pipeline_content:
            print("   ✓ audio_wake_pipeline.py: OWW_THRESHOLD=0.35")
        else:
            print("   ✗ audio_wake_pipeline.py: OWW_THRESHOLD missing")
            all_good = False
            
        if 'OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2)' in pipeline_content:
            print("   ✓ audio_wake_pipeline.py: OWW_CONSECUTIVE=2")
        else:
            print("   ✗ audio_wake_pipeline.py: OWW_CONSECUTIVE missing")
            all_good = False
            
        if 'HOTWORD_RISING_EDGE_DELTA = _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.03)' in pipeline_content:
            print("   ✓ audio_wake_pipeline.py: HOTWORD_RISING_EDGE_DELTA=0.03")
        else:
            print("   ✗ audio_wake_pipeline.py: HOTWORD_RISING_EDGE_DELTA missing")
            all_good = False
    else:
        print("   ✗ audio_wake_pipeline.py not found")
        all_good = False
    
    # 3. Check hotword_engine_manager.py
    print("\n3. Checking hotword_engine_manager.py...")
    manager_path = Path("engine/hotword_engine_manager.py")
    if manager_path.exists():
        with open(manager_path, 'r') as f:
            content = f.read()
        
        if 'self.min_rms = float(self.config.get("min_rms", _env_float("NEXI_HOTWORD_MIN_RMS", 0.010)))' in content:
            print("   ✓ hotword_engine_manager.py: min_rms=0.010")
        else:
            print("   ✗ hotword_engine_manager.py: min_rms missing")
            all_good = False
            
        if 'self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)))' in content:
            print("   ✓ hotword_engine_manager.py: threshold=0.35")
        else:
            print("   ✗ hotword_engine_manager.py: threshold missing")
            all_good = False
            
        if 'self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2)))' in content:
            print("   ✓ hotword_engine_manager.py: consecutive_hits_required=2")
        else:
            print("   ✗ hotword_engine_manager.py: consecutive_hits_required missing")
            all_good = False
            
        if 'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.03)))' in content:
            print("   ✓ hotword_engine_manager.py: rising_edge_delta=0.03")
        else:
            print("   ✗ hotword_engine_manager.py: rising_edge_delta missing")
            all_good = False
    else:
        print("   ✗ hotword_engine_manager.py not found")
        all_good = False
    
    # 4. Check diagnostics.py
    print("\n4. Checking diagnostics.py...")
    diagnostics_path = Path("engine/diagnostics.py")
    if diagnostics_path.exists():
        with open(diagnostics_path, 'r') as f:
            content = f.read()
        
        if 'os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.35")' in content:
            print("   ✓ diagnostics.py: OPENWAKEWORD_SCORE_THRESHOLD=0.35")
        else:
            print("   ✗ diagnostics.py: OPENWAKEWORD_SCORE_THRESHOLD missing")
            all_good = False
    else:
        print("   ✗ diagnostics.py not found")
        all_good = False
    
    # Summary
    print("\n=== VERIFICATION SUMMARY ===")
    if all_good:
        print("✅ SUCCESS: All hotword configuration fixes have been applied correctly!")
        print("\nThe following changes have been successfully implemented:")
        print("1. .env.example updated with:")
        print("   - NEXI_HOTWORD_MIN_RMS=0.010 (increased from 0.003)")
        print("   - OPENWAKEWORD_SCORE_THRESHOLD=0.35 (increased from 0.25)")
        print("   - OPENWAKEWORD_CONSECUTIVE_HITS=2 (increased from 1)")
        print("   - NEXI_HOTWORD_DEBUG=true (added for troubleshooting)")
        print("\n2. audio_wake_pipeline.py updated with:")
        print("   - HOTWORD_MIN_RMS=0.010")
        print("   - HOTWORD_RISING_EDGE_DELTA=0.03")
        print("   - OWW_THRESHOLD=0.35")
        print("   - OWW_CONSECUTIVE=2")
        print("\n3. hotword_engine_manager.py updated with:")
        print("   - min_rms=0.010")
        print("   - threshold=0.35")
        print("   - consecutive_hits_required=2")
        print("   - rising_edge_delta=0.03")
        print("\n4. diagnostics.py updated with:")
        print("   - OPENWAKEWORD_SCORE_THRESHOLD=0.35")
        print("\nThese changes should significantly reduce false positives from random noises.")
        return True
    else:
        print("❌ FAILURE: Some hotword configuration fixes were not applied correctly.")
        print("\nPlease review the configuration files manually.")
        return False

if __name__ == "__main__":
    import sys
    success = verify_hotword_fix()
    sys.exit(0 if success else 1)
