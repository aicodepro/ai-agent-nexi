#!/usr/bin/env python3
"""
Debug script to verify hotword configuration.
"""
import os
from pathlib import Path

def debug_hotword():
    print("=== DEBUGGING HOTWORD CONFIGURATION ===\n")
    
    # Check hotword_engine_manager.py
    manager_path = Path("engine/hotword_engine_manager.py")
    if manager_path.exists():
        with open(manager_path, 'r') as f:
            lines = f.readlines()
        
        print("Contents of hotword_engine_manager.py around the __init__ method:")
        for i, line in enumerate(lines):
            if "self.min_rms = float" in line or "self.rising_edge_delta = float" in line or "self.threshold = float" in line or "self.consecutive_hits_required = int" in line:
                print(f"Line {i+1}: {line.rstrip()}")
        
        # Check specific lines
        print("\n=== CHECKING SPECIFIC LINES ===")
        
        # Line numbers (0-indexed) where we expect the patterns
        expected_patterns = [
            (57, 'self.min_rms = float(self.config.get("min_rms", _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010))))'),
            (58, 'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03))))'),
            (54, 'self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35))))'),
            (55, 'self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2))))')
        ]
        
        all_good = True
        for line_num, expected_pattern in expected_patterns:
            if line_num < len(lines):
                actual_line = lines[line_num - 1].rstrip()
                if actual_line == expected_pattern:
                    print(f"✓ Line {line_num}: Pattern matches exactly")
                else:
                    print(f"✗ Line {line_num}:")
                    print(f"  Expected: {expected_pattern}")
                    print(f"  Actual:   {actual_line}")
                    all_good = False
            else:
                print(f"✗ Line {line_num} not found in file (only {len(lines)} lines)")
                all_good = False
        
        return all_good
    else:
        print("✗ hotword_engine_manager.py not found")
        return False

if __name__ == "__main__":
    import sys
    success = debug_hotword()
    sys.exit(0 if success else 1)
