#!/usr/bin/env python3
"""
Update .env.example with corrected hotword thresholds.
"""
import os
from pathlib import Path

def update_env_example():
    print("=== UPDATING .env.example WITH HOTWORD FIXES ===\n")
    
    env_path = Path("E:\\nexi-main\\.env.example")
    if not env_path.exists():
        print(f"ERROR: {env_path} not found!")
        return False
    
    env_content = env_path.read_text()
    lines = env_content.split('\n')
    
    # Update settings
    updates = [
        ("NEXI_HOTWORD_MIN_RMS", "NEXI_HOTWORD_MIN_RMS=0.010"),
        ("OPENWAKEWORD_SCORE_THRESHOLD", "OPENWAKEWORD_SCORE_THRESHOLD=0.35"),
        ("OPENWAKEWORD_CONSECUTIVE_HITS", "OPENWAKEWORD_CONSECUTIVE_HITS=2"),
        ("NEXI_HOTWORD_DEBUG", "NEXI_HOTWORD_DEBUG=true"),
    ]
    
    updated = False
    for i, line in enumerate(lines):
        line = line.strip()
        if line and not line.startswith('#'):
            for key, new_line in updates:
                if line.startswith(key + '='):
                    lines[i] = new_line
                    print(f"✓ Updated {key}: {line.split('=')[1]} → {new_line.split('=')[1]}")
                    updated = True
                    break
    
    # Write back
    if updated:
        updated_content = '\n'.join(lines)
        env_path.write_text(updated_content)
        print(f"\n✓ Successfully updated {env_path}")
        return True
    else:
        print("\n⚠ No updates were made (lines may already be updated)")
        return False

if __name__ == "__main__":
    update_env_example()