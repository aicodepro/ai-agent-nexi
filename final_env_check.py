#!/usr/bin/env python3
"""
Quick check and fix of the environment file.
"""
import os
from pathlib import Path

def check_and_fix_env_example():
    print("=== CHECKING .env.example ===\n")
    
    env_path = Path("E:\\jarvis-main\\.env.example")
    if not env_path.exists():
        print(f"ERROR: {env_path} not found!")
        return False
    
    env_content = env_path.read_text()
    
    # Add missing JARVIS_HOTWORD_MIN_RMS if not present
    if "JARVIS_HOTWORD_MIN_RMS=" not in env_content:
        # Insert after JARVIS_HOTWORD_DEBUG=true (line 31)
        env_content = env_content.replace(
            "JARVIS_HOTWORD_DEBUG=true\nJARVIS_HOTWORD_PHRASES=hey jarvis,jarvis",
            "JARVIS_HOTWORD_DEBUG=true\nJARVIS_HOTWORD_MIN_RMS=0.010\nJARVIS_HOTWORD_PHRASES=hey jarvis,jarvis"
        )
        print("✓ Added JARVIS_HOTWORD_MIN_RMS=0.010 to .env.example")
    else:
        print("✓ JARVIS_HOTWORD_MIN_RMS already present in .env.example")
    
    # Write back
    env_path.write_text(env_content)
    print("✓ Updated .env.example")
    
    # Verify all required settings
    print("\n=== FINAL VERIFICATION ===")
    
    required_settings = [
        ("JARVIS_HOTWORD_MIN_RMS=0.010", "JARVIS_HOTWORD_MIN_RMS"),
        ("OPENWAKEWORD_SCORE_THRESHOLD=0.35", "OPENWAKEWORD_SCORE_THRESHOLD"),
        ("OPENWAKEWORD_CONSECUTIVE_HITS=2", "OPENWAKEWORD_CONSECUTIVE_HITS"),
        ("JARVIS_HOTWORD_DEBUG=true", "JARVIS_HOTWORD_DEBUG")
    ]
    
    all_good = True
    for setting, name in required_settings:
        if setting in env_content:
            print(f"✓ {name} is correct")
        else:
            print(f"✗ {name} is missing or incorrect")
            all_good = False
    
    if all_good:
        print("\n✅ SUCCESS: All hotword configuration fixes have been applied!")
        print("\nThe following settings have been correctly configured:")
        print("  - JARVIS_HOTWORD_MIN_RMS=0.010 (increased from 0.003 for better noise rejection)")
        print("  - OPENWAKEWORD_SCORE_THRESHOLD=0.35 (increased from 0.25 for better accuracy)")
        print("  - OPENWAKEWORD_CONSECUTIVE_HITS=2 (increased from 1 for more reliability)")
        print("  - JARVIS_HOTWORD_DEBUG=true (for troubleshooting)")
        print("\nThese changes should significantly reduce false positives from random noises.")
        return True
    else:
        print("\n❌ FAILURE: Some hotword configuration settings are incorrect.")
        return False

if __name__ == "__main__":
    import sys
    success = check_and_fix_env_example()
    sys.exit(0 if success else 1)
