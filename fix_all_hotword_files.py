#!/usr/bin/env python3
"""
Fix all hotword configuration files at once.
"""
import os
from pathlib import Path

def fix_all_files():
    print("=== FIXING ALL HOTWORD CONFIGURATION FILES ===\n")
    
    # 1. Fix .env.example
    print("1. Fixing .env.example...")
    env_path = Path("E:\\nexi-main\\.env.example")
    if env_path.exists():
        env_content = env_path.read_text()
        
        # Make sure all required lines are present
        if "NEXI_HOTWORD_MIN_RMS=0.010" not in env_content:
            # Replace the line
            env_content = env_content.replace(
                "NEXI_HOTWORD_MIN_RMS=",
                "NEXI_HOTWORD_MIN_RMS=0.010"
            )
            print("   ✓ Fixed NEXI_HOTWORD_MIN_RMS")
        
        if "OPENWAKEWORD_SCORE_THRESHOLD=0.35" not in env_content:
            env_content = env_content.replace(
                "OPENWAKEWORD_SCORE_THRESHOLD=0.25",
                "OPENWAKEWORD_SCORE_THRESHOLD=0.35"
            )
            print("   ✓ Fixed OPENWAKEWORD_SCORE_THRESHOLD")
        
        if "OPENWAKEWORD_CONSECUTIVE_HITS=2" not in env_content:
            env_content = env_content.replace(
                "OPENWAKEWORD_CONSECUTIVE_HITS=1",
                "OPENWAKEWORD_CONSECUTIVE_HITS=2"
            )
            print("   ✓ Fixed OPENWAKEWORD_CONSECUTIVE_HITS")
        
        if "NEXI_HOTWORD_DEBUG=true" not in env_content:
            # Find the line and add after it
            lines = env_content.split('\n')
            for i, line in enumerate(lines):
                if line.strip() == "NEXI_HOTWORD_ENABLED=true":
                    lines.insert(i + 1, "NEXI_HOTWORD_DEBUG=true")
                    print("   ✓ Added NEXI_HOTWORD_DEBUG=true")
                    break
            env_content = '\n'.join(lines)
        
        env_path.write_text(env_content)
        print("   ✓ Updated .env.example")
    
    # 2. Fix audio_wake_pipeline.py
    print("\n2. Fixing audio_wake_pipeline.py...")
    pipeline_path = Path("E:\\nexi-main\\engine\\audio_wake_pipeline.py")
    if pipeline_path.exists():
        pipeline_content = pipeline_path.read_text()
        
        # Update all constants
        pipeline_content = pipeline_content.replace(
            'HOTWORD_MIN_RMS = _env_float("NEXI_HOTWORD_MIN_RMS", 0.003)',
            'HOTWORD_MIN_RMS = _env_float("NEXI_HOTWORD_MIN_RMS", 0.010)'
        )
        
        pipeline_content = pipeline_content.replace(
            'HOTWORD_RISING_EDGE_DELTA = _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.02)',
            'HOTWORD_RISING_EDGE_DELTA = _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.03)'
        )
        
        pipeline_content = pipeline_content.replace(
            'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.25)',
            'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)'
        )
        
        pipeline_content = pipeline_content.replace(
            'OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 1)',
            'OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2)'
        )
        
        pipeline_path.write_text(pipeline_content)
        print("   ✓ Updated audio_wake_pipeline.py")
    
    # 3. Fix hotword_engine_manager.py
    print("\n3. Fixing hotword_engine_manager.py...")
    manager_path = Path("E:\\nexi-main\\engine\\hotword_engine_manager.py")
    if manager_path.exists():
        manager_content = manager_path.read_text()
        
        # Update the __init__ method defaults
        manager_content = manager_content.replace(
            'self.min_rms = float(self.config.get("min_rms", _env_float("NEXI_HOTWORD_MIN_RMS", 0.003))))',
            'self.min_rms = float(self.config.get("min_rms", _env_float("NEXI_HOTWORD_MIN_RMS", 0.010))))'
        )
        
        manager_content = manager_content.replace(
            'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.02))))',
            'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.03))))'
        )
        
        manager_content = manager_content.replace(
            'self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.25))))',
            'self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35))))'
        )
        
        manager_content = manager_content.replace(
            'self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 1))))',
            'self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2))))'
        )
        
        manager_path.write_text(manager_content)
        print("   ✓ Updated hotword_engine_manager.py")
    
    # 4. Fix diagnostics.py
    print("\n4. Fixing diagnostics.py...")
    diagnostics_path = Path("E:\\nexi-main\\engine\\diagnostics.py")
    if diagnostics_path.exists():
        diagnostics_content = diagnostics_path.read_text()
        
        diagnostics_content = diagnostics_content.replace(
            'os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.25")',
            'os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.35")'
        )
        
        diagnostics_path.write_text(diagnostics_content)
        print("   ✓ Updated diagnostics.py")
    
    print("\n=== ALL FILES FIXED ===")
    print("\nSummary of changes:")
    print("1. .env.example: Updated hotword thresholds and added debug flag")
    print("2. audio_wake_pipeline.py: Updated HOTWORD_MIN_RMS, HOTWORD_RISING_EDGE_DELTA, OWW_THRESHOLD, OWW_CONSECUTIVE")
    print("3. hotword_engine_manager.py: Updated all defaults in __init__ method")
    print("4. diagnostics.py: Updated OPENWAKEWORD_SCORE_THRESHOLD in reporting")
    print("\nThese changes should significantly reduce false positives from random noises.")

if __name__ == "__main__":
    import sys
    fix_all_files()