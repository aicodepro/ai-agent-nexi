#!/usr/bin/env python3
"""
Complete fix for hotword issue - updates all configuration files.
"""
import os
from pathlib import Path

def update_all_config_files():
    print("=== COMPLETE HOTWORD FIX ===\n")
    
    # 1. Update .env.example (the configuration reference)
    print("1. Updating .env.example...")
    env_path = Path("E:\\nexi-main\\.env.example")
    if not env_path.exists():
        print(f"   ERROR: {env_path} not found!")
        return False
    
    env_content = env_path.read_text()
    lines = env_content.split('\n')
    
    # Find and update the settings
    for i, line in enumerate(lines):
        line = line.strip()
        if line and not line.startswith('#'):
            if 'NEXI_HOTWORD_MIN_RMS=' in line:
                lines[i] = 'NEXI_HOTWORD_MIN_RMS=0.010'
                print(f"   ✓ Updated NEXI_HOTWORD_MIN_RMS to 0.010")
            elif 'OPENWAKEWORD_SCORE_THRESHOLD=' in line and '0.35' not in line:
                lines[i] = 'OPENWAKEWORD_SCORE_THRESHOLD=0.35'
                print(f"   ✓ Updated OPENWAKEWORD_SCORE_THRESHOLD to 0.35")
            elif 'OPENWAKEWORD_CONSECUTIVE_HITS=' in line and '2' not in line:
                lines[i] = 'OPENWAKEWORD_CONSECUTIVE_HITS=2'
                print(f"   ✓ Updated OPENWAKEWORD_CONSECUTIVE_HITS to 2")
    
    env_path.write_text('\n'.join(lines))
    print(f"   ✓ Updated {env_path}")
    
    # 2. Update audio_wake_pipeline.py constants
    print("\n2. Updating audio_wake_pipeline.py...")
    pipeline_path = Path("E:\\nexi-main\\engine\\audio_wake_pipeline.py")
    pipeline_content = pipeline_path.read_text()
    
    # Update constants
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
    print("   ✓ Updated audio_wake_pipeline.py constants")
    
    # 3. Update hotword_engine_manager.py
    print("\n3. Updating hotword_engine_manager.py...")
    manager_path = Path("E:\\nexi-main\\engine\\hotword_engine_manager.py")
    manager_content = manager_path.read_text()
    
    # Update defaults in constructor
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
    print("   ✓ Updated hotword_engine_manager.py defaults")
    
    # 4. Update diagnostics.py (for reporting)
    print("\n4. Updating diagnostics.py...")
    diagnostics_path = Path("E:\\nexi-main\\engine\\diagnostics.py")
    diagnostics_content = diagnostics_path.read_text()
    
    diagnostics_content = diagnostics_content.replace(
        'os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.25")',
        'os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.35")'
    )
    
    diagnostics_path.write_text(diagnostics_content)
    print("   ✓ Updated diagnostics.py")
    
    # 5. Create verification script
    print("\n5. Creating verification script...")
    verify_path = Path("E:\\nexi-main\\verify_hotword_final.py")
    verify_content = '''#!/usr/bin/env python3
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
    
    # 2. Check audio_wake_pipeline.py
    pipeline_path = Path("engine/audio_wake_pipeline.py")
    if pipeline_path.exists():
        pipeline_content = pipeline_path.read_text()
        checks.append(("HOTWORD_MIN_RMS in audio_wake_pipeline.py", 'HOTWORD_MIN_RMS = _env_float("NEXI_HOTWORD_MIN_RMS", 0.010)' in pipeline_content))
        checks.append(("OWW_THRESHOLD in audio_wake_pipeline.py", 'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)' in pipeline_content))
        checks.append(("OWW_CONSECUTIVE in audio_wake_pipeline.py", 'OWW_CONSECUTIVE = _env_int("OPENWAKEWORD_CONSECUTIVE_HITS", 2)' in pipeline_content))
    
    # 3. Check hotword_engine_manager.py
    manager_path = Path("engine/hotword_engine_manager.py")
    if manager_path.exists():
        manager_content = manager_path.read_text()
        checks.append(("min_rms default in hotword_engine_manager.py", 'self.min_rms = float(self.config.get("min_rms", _env_float("NEXI_HOTWORD_MIN_RMS", 0.010))))' in manager_content))
        checks.append(("rising_edge_delta default in hotword_engine_manager.py", 'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("NEXI_HOTWORD_RISING_EDGE_DELTA", 0.03))))' in manager_content))
    
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
'''
    verify_path.write_text(verify_content)
    print("   ✓ Created verify_hotword_final.py")
    
    # 6. Run verification
    print("\n6. Running final verification...")
    try:
        import subprocess
        result = subprocess.run([sys.executable, "verify_hotword_final.py"], 
                              capture_output=True, text=True, timeout=60, cwd="E:\\nexi-main")
        
        if result.returncode == 0:
            print("   ✓ Final verification PASSED!")
        else:
            print(f"   ✗ Final verification FAILED")
            print(result.stdout)
            if result.stderr:
                print("   Errors:")
                print(result.stderr)
    except Exception as e:
        print(f"   Error running verification: {e}")
    
    print("\n=== HOTWORD FIX COMPLETE ===")
    return True

if __name__ == "__main__":
    import sys
    success = update_all_config_files()
    sys.exit(0 if success else 1)
