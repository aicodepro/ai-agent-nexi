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
    
    # Add missing NEXI_HOTWORD_MIN_RMS if not present
    if "NEXI_HOTWORD_MIN_RMS=" not in env_content:
        # Insert after NEXI_HOTWORD_DEBUG=true (line 31)
        env_content = env_content.replace(
            "NEXI_HOTWORD_DEBUG=true\nNEXI_HOTWORD_PHRASES=hey nexi,nexi",
            "NEXI_HOTWORD_DEBUG=true\nNEXI_HOTWORD_MIN_RMS=0.010\nNEXI_HOTWORD_PHRASES=hey nexi,nexi"
        )
        print("✓ Added NEXI_HOTWORD_MIN_RMS=0.010 to .env.example")
    else:
        print("✓ NEXI_HOTWORD_MIN_RMS already present in .env.example")
    
    # Write back
    env_path.write_text(env_content)
    print("✓ Updated .env.example")
    
    # Verify all required settings
    print("\n=== FINAL VERIFICATION ===")
    
    required_settings = [
        ("NEXI_HOTWORD_MIN_RMS=0.010", "NEXI_HOTWORD_MIN_RMS"),
        ("OPENWAKEWORD_SCORE_THRESHOLD=0.35", "OPENWAKEWORD_SCORE_THRESHOLD"),
        ("OPENWAKEWORD_CONSECUTIVE_HITS=2", "OPENWAKEWORD_CONSECUTIVE_HITS"),
        ("NEXI_HOTWORD_DEBUG=true", "NEXI_HOTWORD_DEBUG")
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
        print("  - NEXI_HOTWORD_MIN_RMS=0.010 (increased from 0.003 for better noise rejection)")
        print("  - OPENWAKEWORD_SCORE_THRESHOLD=0.35 (increased from 0.25 for better accuracy)")
        print("  - OPENWAKEWORD_CONSECUTIVE_HITS=2 (increased from 1 for more reliability)")
        print("  - NEXI_HOTWORD_DEBUG=true (for troubleshooting)")
        print("\nThese changes should significantly reduce false positives from random noises.")
        return True
    else:
        print("\n❌ FAILURE: Some hotword configuration settings are incorrect.")
        return False

if __name__ == "__main__":
    import sys
    success = check_and_fix_env_example()
    sys.exit(0 if success else 1)
