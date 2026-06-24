#!/usr/bin/env python3
"""
Final verification that hotword fix has been applied correctly.
"""
import os
from pathlib import Path

def verify_hotword_final():
    print("=== FINAL HOTWORD VERIFICATION ===\n")
    
    # Check all configuration files
    checks = []
    
    # 1. Check .env.example
    env_path = Path(".env.example")
    if env_path.exists():
        env_content = env_path.read_text()
        checks.append(("NEXI_HOTWORD_MIN_RMS in .env.example", "NEXI_HOTWORD_MIN_RMS=0.010" in env_content))
        checks.append(("OPENWAKEWORD_SCORE_THRESHOLD in .env.example", "OPENWAKEWORD_SCORE_THRESHOLD=0.35" in env_content))
        checks.append(("OPENWAKEWORD_CONSECUTIVE_HITS in .env.example", "OPENWAKEWORD_CONSECUTIVE_HITS=2" in env_content))
        checks.append(("NEXI_HOTWORD_DEBUG in .env.example", "NEXI_HOTWORD_DEBUG=true" in env_content))
    
    # 2. Check audio_wake_pipeline.py
    pipeline_path = Path("engine/audio_wake_pipeline.py")
    if pipeline_path.exists():
        pipeline_content = pipeline_path.read_text()
        checks.append(("HOTWORD_MIN_RMS in audio_wake_pipeline.py", 'HOTWORD_MIN_RMS = _env_float("NEXI_HOTWORD_MIN_RMS", 0.010)' in pipeline_content))
        checks.append(("OWW_THRESHOLD in audio_wake_pipeline.py", 'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)' in pipeline_content))
        checks.append(("OWW_CONSECUTIVE in audio_wake_pipeline.py", 'OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2)' in pipeline_content))
        checks.append(("HOTWORD_RISING_EDGE_DELTA in audio_wake_pipeline.py", 'HOTWORD_RISING_EDGE_DELTA = _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.03)' in pipeline_content))
    
    # 3. Check hotword_engine_manager.py
    manager_path = Path("engine/hotword_engine_manager.py")
    if manager_path.exists():
        manager_content = manager_path.read_text()
        # Check the exact string in the __init__ method
        checks.append(("min_rms default in hotword_engine_manager.py", 'self.min_rms = float(self.config.get("min_rms", _env_float("NEXI_HOTWORD_MIN_RMS", 0.010))))' in manager_content))
        checks.append(("rising_edge_delta default in hotword_engine_manager.py", 'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.03))))' in manager_content))
        checks.append(("threshold default in hotword_engine_manager.py", 'self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35))))' in manager_content))
        checks.append(("consecutive_hits_required default in hotword_engine_manager.py", 'self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2))))' in manager_content))
    
    # Print results
    all_passed = True
    print("1. Configuration File Checks:")
    for check_name, passed in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"   {status}: {check_name}")
        if not passed:
            all_passed = False
    
    print("\n2. Summary:")
    if all_passed:
        print("   ✓ All checks passed! Hotword fix has been successfully applied.")
        print("\n   Improvements implemented:")
        print("   - NEXI_HOTWORD_MIN_RMS increased from 0.003 to 0.010 (better noise rejection)")
        print("   - OPENWAKEWORD_SCORE_THRESHOLD increased from 0.25 to 0.35 (better accuracy)")
        print("   - OPENWAKEWORD_CONSECUTIVE_HITS increased from 1 to 2 (more reliable detection)")
        print("   - HOTWORD_RISING_EDGE_DELTA increased from 0.02 to 0.03 (better signal discrimination)")
        print("\n   These changes should significantly reduce false positives from random noises.")
        return True
    else:
        print("   ✗ Some checks failed. Please review the fixes.")
        return False

if __name__ == "__main__":
    verify_hotword_final()
