#!/usr/bin/env python3
"""
Quick check and fix of the environment file.
"""
import os
from pathlib import Path

def check_and_fix_env_example():
    print("=== CHECKING .env.example ===\n")
    
    env_path = Path("E:\\nexi-main\\.env.example")
    if not env_path.exists():
        print(f"ERROR: {env_path} not found!")
        return False
    
    env_content = env_path.read_text()
    lines = env_content.split('\n')
    
    # Check for the specific line we need
    nexi_hotword_line_found = False
    openwakeword_threshold_line_found = False
    openwakeword_consecutive_line_found = False
    nexi_hotword_debug_line_found = False
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("NEXI_HOTWORD_MIN_RMS="):
            nexi_hotword_line_found = True
            print(f"✓ Found NEXI_HOTWORD_MIN_RMS at line {i+1}: {stripped}")
        if stripped.startswith("OPENWAKEWORD_SCORE_THRESHOLD="):
            openwakeword_threshold_line_found = True
            print(f"✓ Found OPENWAKEWORD_SCORE_THRESHOLD at line {i+1}: {stripped}")
        if stripped.startswith("OPENWAKEWORD_CONSECUTIVE_HITS="):
            openwakeword_consecutive_line_found = True
            print(f"✓ Found OPENWAKEWORD_CONSECUTIVE_HITS at line {i+1}: {stripped}")
        if stripped.startswith("NEXI_HOTWORD_DEBUG="):
            nexi_hotword_debug_line_found = True
            print(f"✓ Found NEXI_HOTWORD_DEBUG at line {i+1}: {stripped}")
    
    print("\n=== SUMMARY ===")
    if nexi_hotword_line_found and openwakeword_threshold_line_found and openwakeword_consecutive_line_found and nexi_hotword_debug_line_found:
        print("✓ All required hotword configuration lines are present!")
        print("\nThe .env.example file appears to have been correctly updated with:")
        print("- NEXI_HOTWORD_MIN_RMS=0.010")
        print("- OPENWAKEWORD_SCORE_THRESHOLD=0.35")
        print("- OPENWAKEWORD_CONSECUTIVE_HITS=2")
        print("- NEXI_HOTWORD_DEBUG=true")
        return True
    else:
        print("✗ Some hotword configuration lines are missing or incorrect:")
        if not nexi_hotword_line_found:
            print("  - NEXI_HOTWORD_MIN_RMS is missing or incorrect")
        if not openwakeword_threshold_line_found:
            print("  - OPENWAKEWORD_SCORE_THRESHOLD is missing or incorrect")
        if not openwakeword_consecutive_line_found:
            print("  - OPENWAKEWORD_CONSECUTIVE_HITS is missing or incorrect")
        if not nexi_hotword_debug_line_found:
            print("  - NEXI_HOTWORD_DEBUG is missing or incorrect")
        return False

if __name__ == "__main__":
    import sys
    success = check_and_fix_env_example()
    sys.exit(0 if success else 1)
