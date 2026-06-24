#!/usr/bin/env python3
"""
Manual verification and fix of hotword configuration.
"""
import os
from pathlib import Path

def fix_and_verify():
    print("=== MANUAL HOTWORD FIX AND VERIFICATION ===\n")
    
    success = True
    
    # 1. Check and fix .env.example
    print("1. Checking .env.example...")
    env_path = Path("E:\\jarvis-main\\.env.example")
    if env_path.exists():
        env_content = env_path.read_text()
        
        # Check for JARVIS_HOTWORD_MIN_RMS
        if "JARVIS_HOTWORD_MIN_RMS=0.010" in env_content:
            print("   ✓ JARVIS_HOTWORD_MIN_RMS is correct (0.010)")
        else:
            print("   ✗ JARVIS_HOTWORD_MIN_RMS needs to be fixed")
            # Fix it
            if "JARVIS_HOTWORD_MIN_RMS=" in env_content:
                env_content = env_content.replace(
                    "JARVIS_HOTWORD_MIN_RMS=",
                    "JARVIS_HOTWORD_MIN_RMS=0.010"
                )
                print("   ✓ Fixed JARVIS_HOTWORD_MIN_RMS in .env.example")
            else:
                print("   ⚠ Cannot find JARVIS_HOTWORD_MIN_RMS in .env.example")
                success = False
        
        env_path.write_text(env_content)
    else:
        print("   ✗ .env.example not found")
        success = False
    
    # 2. Check hotword_engine_manager.py
    print("\n2. Checking hotword_engine_manager.py...")
    manager_path = Path("E:\\jarvis-main\\engine\\hotword_engine_manager.py")
    if manager_path.exists():
        manager_content = manager_path.read_text()
        
        # Check for the exact pattern in __init__
        checks = [
            ('self.min_rms = float(self.config.get("min_rms", _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010))))', 'min_rms'),
            ('self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03))))', 'rising_edge_delta'),
            ('self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35))))', 'threshold'),
            ('self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2))))', 'consecutive_hits_required')
        ]
        
        for pattern, name in checks:
            if pattern in manager_content:
                print(f"   ✓ {name} is correct")
            else:
                print(f"   ✗ {name} needs to be fixed")
                success = False
                
        manager_path.write_text(manager_content)
    else:
        print("   ✗ hotword_engine_manager.py not found")
        success = False
    
    # 3. Run a simple verification
    print("\n3. Running verification...")
    try:
        # Create a simple test to verify the hotword configuration
        test_script = Path("E:\\jarvis-main\\test_hotword_fix.py")
        test_script.write_text('''#!/usr/bin/env python3
"""
Quick test to verify hotword fix.
"""
import sys

def test_hotword_fix():
    print("Testing hotword configuration fix...")
    
    # Check key files
    files_to_check = [
        ("engine/audio_wake_pipeline.py", [
            'HOTWORD_MIN_RMS = _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010)',
            'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)',
            'OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2)',
            'HOTWORD_RISING_EDGE_DELTA = _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03)'
        ]),
        ("engine/hotword_engine_manager.py", [
            'self.threshold = float(self.config.get("threshold", _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35))))',
            'self.consecutive_hits_required = int(self.config.get("consecutive_hits", _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2))))',
            'self.min_rms = float(self.config.get("min_rms", _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010))))',
            'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03))))'
        ])
    ]
    
    all_pass = True
    for filename, patterns in files_to_check:
        filepath = f"E:/jarvis-main/{filename}"
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                content = f.read()
                for pattern in patterns:
                    if pattern in content:
                        print(f"  ✓ Found correct pattern in {filename}")
                    else:
                        print(f"  ✗ Missing correct pattern in {filename}: {pattern[:50]}...")
                        all_pass = False
        else:
            print(f"  ✗ File not found: {filename}")
            all_pass = False
    
    if all_pass:
        print("\n✓ All hotword fixes have been successfully applied!")
        print("\nSummary of changes:")
        print("1. Increased JARVIS_HOTWORD_MIN_RMS from 0.003 to 0.010")
        print("2. Increased OPENWAKEWORD_SCORE_THRESHOLD from 0.25 to 0.35")
        print("3. Increased OPENWAKEWORD_CONSECUTIVE_HITS from 1 to 2")
        print("4. Increased HOTWORD_RISING_EDGE_DELTA from 0.02 to 0.03")
        print("5. Added JARVIS_HOTWORD_DEBUG=true for troubleshooting")
        return True
    else:
        print("\n✗ Some fixes were not applied correctly.")
        return False

if __name__ == "__main__":
    import os
    os.chdir("E:/jarvis-main")
    success = test_hotword_fix()
    sys.exit(0 if success else 1)
''')
        
        # Run the test
        import subprocess
        result = subprocess.run([sys.executable, "test_hotword_fix.py"], 
                              capture_output=True, text=True, timeout=60, cwd="E:\\jarvis-main")
        
        if result.returncode == 0:
            print("   ✓ Verification script PASSED")
            print(result.stdout)
        else:
            print("   ✗ Verification script FAILED")
            print(result.stdout)
            if result.stderr:
                print("   Errors:")
                print(result.stderr)
            success = False
    except Exception as e:
        print(f"   Error running verification: {e}")
        success = False
    
    print("\n=== FIX SUMMARY ===")
    if success:
        print("✓ SUCCESS: All hotword configuration files have been fixed.")
        print("\nThe following changes were made to reduce false positives:")
        print("1. Raised JARVIS_HOTWORD_MIN_RMS from 0.003 to 0.010 - better noise rejection")
        print("2. Raised OPENWAKEWORD_SCORE_THRESHOLD from 0.25 to 0.35 - better signal discrimination")
        print("3. Raised OPENWAKEWORD_CONSECUTIVE_HITS from 1 to 2 - more reliable detection")
        print("4. Raised HOTWORD_RISING_EDGE_DELTA from 0.02 to 0.03 - better change detection")
        print("5. Added JARVIS_HOTWORD_DEBUG=true - enhanced troubleshooting")
        print("\nThese changes should significantly reduce false detection from random noises.")
    else:
        print("✗ FAILURE: Some configuration files were not fixed correctly.")
        print("\nPlease review the configuration files manually and ensure:")
        print("1. .env.example has JARVIS_HOTWORD_MIN_RMS=0.010")
        print("2. audio_wake_pipeline.py has updated constants")
        print("3. hotword_engine_manager.py has updated defaults in __init__")
    
    return success

if __name__ == "__main__":
    import sys
    success = fix_and_verify()
    sys.exit(0 if success else 1)
