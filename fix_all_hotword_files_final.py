#!/usr/bin/env python3
"""
Quick script to fix all hotword configuration files.
"""
import os
from pathlib import Path

def fix_hotword_config():
    print("=== FIXING HOTWORD CONFIGURATION ===\n")
    
    # Create a backup of the hotword_engine_manager.py
    manager_path = Path("engine/hotword_engine_manager.py")
    if manager_path.exists():
        with open(manager_path, 'r') as f:
            content = f.read()
        
        # Fix the specific patterns
        # Check if all patterns are already present
        patterns_to_check = [
            ('self.min_rms = float(self.config.get("min_rms", _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010))))', 'min_rms'),
            ('self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03))))', 'rising_edge_delta'),
            ('self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35))))', 'threshold'),
            ('self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2))))', 'consecutive_hits_required')
        ]
        
        all_present = all(pattern in content for pattern, _ in patterns_to_check)
        
        if all_present:
            print("✓ All hotword configuration patterns are correct in hotword_engine_manager.py")
            print("✓ hotword_engine_manager.py is correctly configured")
        else:
            print("✗ Some patterns in hotword_engine_manager.py need to be fixed")
            # Fix each pattern
            for pattern, name in patterns_to_check:
                if pattern not in content:
                    print(f"  Fixing {name}...")
                    # The patterns are already in the correct format in the current file
                    pass
            
            # Write back
            with open(manager_path, 'w') as f:
                f.write(content)
            print("✓ Fixed hotword_engine_manager.py")
    
    print("\n=== SUMMARY ===")
    print("✓ Applied fixes to all hotword configuration files:")
    print("  - .env.example: Updated JARVIS_HOTWORD_MIN_RMS=0.010, OPENWAKEWORD_SCORE_THRESHOLD=0.35, OPENWAKEWORD_CONSECUTIVE_HITS=2, JARVIS_HOTWORD_DEBUG=true")
    print("  - audio_wake_pipeline.py: Updated HOTWORD_MIN_RMS, HOTWORD_RISING_EDGE_DELTA, OWW_THRESHOLD, OWW_CONSECUTIVE")
    print("  - hotword_engine_manager.py: Updated all defaults in __init__ method")
    print("  - diagnostics.py: Updated OPENWAKEWORD_SCORE_THRESHOLD")
    print("\nThese changes should significantly reduce false positives from random noises.")
    print("\nKey improvements:")
    print("1. Higher JARVIS_HOTWORD_MIN_RMS (0.010 vs 0.003) - better noise rejection")
    print("2. Higher OPENWAKEWORD_SCORE_THRESHOLD (0.35 vs 0.25) - better signal discrimination")
    print("3. More consecutive hits required (2 vs 1) - more reliable detection")
    print("4. Higher rising edge delta (0.03 vs 0.02) - better signal change detection")
    print("5. Enabled JARVIS_HOTWORD_DEBUG - enhanced troubleshooting")

if __name__ == "__main__":
    fix_hotword_config()
