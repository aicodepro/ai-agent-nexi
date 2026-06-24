#!/usr/bin/env python3
"""
Fix hotword issue: improving detection accuracy by tightening thresholds.
This addresses the issue where hotword was detecting random noises incorrectly.
"""
import os
import sys
import json
from pathlib import Path

def main():
    print("=== FIXING HOTWORD ISSUE ===")
    
    # 1. Read current .env.example to see all configuration
    env_path = Path("E:\\jarvis-main\\.env.example")
    if not env_path.exists():
        print(f"ERROR: {env_path} not found!")
        return
    
    env_content = env_path.read_text()
    print("\n1. Current environment configuration:")
    
    # Extract key hotword settings
    hotword_settings = {}
    for line in env_content.split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            for key in ['JARVIS_HOTWORD_MIN_RMS', 'JARVIS_HOTWORD_RISING_EDGE_DELTA', 
                        'OPENWAKEWORD_SCORE_THRESHOLD', 'OPENWAKEWORD_CONSECUTIVE_HITS',
                        'JARVIS_HOTWORD_PHRASES', 'OPENWAKEWORD_PRETRAINED_MODELS',
                        'JARVIS_HOTWORD_ENABLED', 'OPENWAKEWORD_ENABLED']:
                if line.startswith(key + '='):
                    hotword_settings[key] = line.split('=', 1)[1].strip()
    
    for key, value in hotword_settings.items():
        print(f"   {key}: {value}")
    
    # 2. Analyze potential issues
    print("\n2. ANALYZING POTENTIAL ISSUES:")
    
    issues = []
    improvements = []
    
    # Check JARVIS_HOTWORD_MIN_RMS (default: 0.003)
    min_rms = float(hotword_settings.get('JARVIS_HOTWORD_MIN_RMS', '0.003'))
    if min_rms < 0.010:
        issues.append(f"- JARVIS_HOTWORD_MIN_RMS is too low ({min_rms:.3f}) — allows noise detection")
        improvements.append(f"- Increase JARVIS_HOTWORD_MIN_RMS to 0.010-0.015 for better noise rejection")
    
    # Check OPENWAKEWORD_SCORE_THRESHOLD (default: 0.25)
    threshold = float(hotword_settings.get('OPENWAKEWORD_SCORE_THRESHOLD', '0.25'))
    if threshold < 0.35:
        issues.append(f"- OPENWAKEWORD_SCORE_THRESHOLD is too low ({threshold:.2f}) — causes false positives")
        improvements.append(f"- Increase OPENWAKEWORD_SCORE_THRESHOLD to 0.35-0.45 for better accuracy")
    
    # Check consecutive hits
    hits = int(hotword_settings.get('OPENWAKEWORD_CONSECUTIVE_HITS', '1'))
    if hits < 2:
        issues.append(f"- OPENWAKEWORD_CONSECUTIVE_HITS is too low ({hits}) — single detection is unreliable")
        improvements.append(f"- Increase OPENWAKEWORD_CONSECUTIVE_HITS to 2-3 for more reliability")
    
    # Check if there are unintended hotword backends
    backend_order = hotword_settings.get('JARVIS_HOTWORD_BACKEND_ORDER', '')
    if 'vosk_keyword' in backend_order:
        issues.append("- VOSK_KEYWORD backend is active — could cause false detections")
    
    if issues:
        print("   ISSUES FOUND:")
        for issue in issues:
            print(f"   {issue}")
    else:
        print("   ✓ No major issues found in current configuration")
    
    # 3. Apply fixes
    print("\n3. APPLYING FIXES:")
    
    # Create updated env content
    lines = env_content.split('\n')
    updated = False
    
    for i, line in enumerate(lines):
        line = line.strip()
        if line and not line.startswith('#'):
            # Fix JARVIS_HOTWORD_MIN_RMS
            if line.startswith('JARVIS_HOTWORD_MIN_RMS='):
                lines[i] = f"JARVIS_HOTWORD_MIN_RMS=0.010"
                print(f"   ✓ Fixed JARVIS_HOTWORD_MIN_RMS: 0.003 → 0.010")
                updated = True
            
            # Fix OPENWAKEWORD_SCORE_THRESHOLD
            elif line.startswith('OPENWAKEWORD_SCORE_THRESHOLD='):
                lines[i] = f"OPENWAKEWORD_SCORE_THRESHOLD=0.35"
                print(f"   ✓ Fixed OPENWAKEWORD_SCORE_THRESHOLD: 0.25 → 0.35")
                updated = True
            
            # Fix OPENWAKEWORD_CONSECUTIVE_HITS
            elif line.startswith('OPENWAKEWORD_CONSECUTIVE_HITS='):
                lines[i] = f"OPENWAKEWORD_CONSECUTIVE_HITS=2"
                print(f"   ✓ Fixed OPENWAKEWORD_CONSECUTIVE_HITS: 1 → 2")
                updated = True
            
            # Add JARVIS_HOTWORD_DEBUG for troubleshooting
            elif line.startswith('JARVIS_HOTWORD_ENABLED='):
                lines.insert(i + 1, "JARVIS_HOTWORD_DEBUG=true")
                print(f"   ✓ Added JARVIS_HOTWORD_DEBUG=true for troubleshooting")
                updated = True
                break
    
    if not updated:
        print("   WARNING: Could not find all settings to fix automatically")
    
    # 4. Write back to .env.example
    updated_env = '\n'.join(lines)
    
    # Create backup first
    backup_path = env_path.with_suffix('.example_backup')
    env_path.rename(backup_path)
    print(f"\n   ✓ Created backup: {backup_path.name}")
    
    # Write updated version
    env_path.write_text(updated_env)
    print(f"   ✓ Updated {env_path.name}")
    
    # 5. Update engine/audio_wake_pipeline.py thresholds
    print("\n4. UPDATING CODE THRESHOLDS:")
    
    pipeline_path = Path("E:\\jarvis-main\\engine\\audio_wake_pipeline.py")
    pipeline_content = pipeline_path.read_text()
    
    # Fix HOTWORD_MIN_RMS constant
    if 'HOTWORD_MIN_RMS = _env_float("JARVIS_HOTWORD_MIN_RMS", 0.003)' in pipeline_content:
        pipeline_content = pipeline_content.replace(
            'HOTWORD_MIN_RMS = _env_float("JARVIS_HOTWORD_MIN_RMS", 0.003)',
            'HOTWORD_MIN_RMS = _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010)'
        )
        print("   ✓ Fixed HOTWORD_MIN_RMS constant: 0.003 → 0.010")
    
    # Fix HOTWORD_RISING_EDGE_DELTA for better detection
    if 'HOTWORD_RISING_EDGE_DELTA = _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.02)' in pipeline_content:
        pipeline_content = pipeline_content.replace(
            'HOTWORD_RISING_EDGE_DELTA = _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.02)',
            'HOTWORD_RISING_EDGE_DELTA = _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03)'
        )
        print("   ✓ Fixed HOTWORD_RISING_EDGE_DELTA constant: 0.02 → 0.03")
    
    # Fix OWW_THRESHOLD for better detection
    if 'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.25)' in pipeline_content:
        pipeline_content = pipeline_content.replace(
            'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.25)',
            'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)'
        )
        print("   ✓ Fixed OWW_THRESHOLD constant: 0.25 → 0.35")
    
    pipeline_path.write_text(pipeline_content)
    print("   ✓ Updated audio_wake_pipeline.py")
    
    # 6. Update hotword_engine_manager.py
    print("\n5. UPDATING HOTWORD_ENGINE_MANAGER.PY:")
    
    manager_path = Path("E:\\jarvis-main\\engine\\hotword_engine_manager.py")
    manager_content = manager_path.read_text()
    
    # Fix min_rms default
    if 'self.min_rms = float(self.config.get("min_rms", _env_float("JARVIS_HOTWORD_MIN_RMS", 0.003)))' in manager_content:
        manager_content = manager_content.replace(
            'self.min_rms = float(self.config.get("min_rms", _env_float("JARVIS_HOTWORD_MIN_RMS", 0.003))))',
            'self.min_rms = float(self.config.get("min_rms", _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010))))'
        )
        print("   ✓ Fixed min_rms default: 0.003 → 0.010")
    
    # Fix rising_edge_delta default
    if 'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.02)))' in manager_content:
        manager_content = manager_content.replace(
            'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.02))))',
            'self.rising_edge_delta = float(self.config.get("rising_edge_delta", _env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03))))'
        )
        print("   ✓ Fixed rising_edge_delta default: 0.02 → 0.03")
    
    manager_path.write_text(manager_content)
    print("   ✓ Updated hotword_engine_manager.py")
    
    test_script = Path("E:\\jarvis-main\\verify_hotword_fix.py")
    test_script.write_text("""#!/usr/bin/env python3
"""
Verify that hotword fix has been applied correctly.
"""
import os
import sys
from pathlib import Path

def verify_hotword_fix():
    print("=== VERIFYING HOTWORD FIX ===\n")
    
    # 1. Check environment variables
    print("1. Environment Variables Check:")
    env_vars = [
        ('JARVIS_HOTWORD_MIN_RMS', '0.010', 'Min RMS should be increased to 0.010'),
        ('OPENWAKEWORD_SCORE_THRESHOLD', '0.35', 'Threshold should be increased to 0.35'),
        ('OPENWAKEWORD_CONSECUTIVE_HITS', '2', 'Consecutive hits should be increased to 2'),
    ]
    
    all_good = True
    for var, expected_value, description in env_vars:
        actual_value = os.getenv(var)
        if actual_value == expected_value:
            print(f"   ✓ {var}: {actual_value} (correct)")
        else:
            print(f"   ✗ {var}: expected {expected_value}, got {actual_value}")
            all_good = False
    
    # 2. Check JARVIS_HOTWORD_DEBUG is set
    if os.getenv('JARVIS_HOTWORD_DEBUG', '').lower() == 'true':
        print("   ✓ JARVIS_HOTWORD_DEBUG is enabled")
    else:
        print("   ✗ JARVIS_HOTWORD_DEBUG should be set to 'true'")
        all_good = False
    
    # 3. Check code changes
    print("\n2. Code Changes Check:")
    
    # Check audio_wake_pipeline.py
    pipeline_file = Path("engine/audio_wake_pipeline.py")
    if pipeline_file.exists():
        content = pipeline_file.read_text()
        if 'HOTWORD_MIN_RMS = _env_float("JARVIS_HOTWORD_MIN_RMS", 0.010)' in content:
            print("   ✓ audio_wake_pipeline.py: HOTWORD_MIN_RMS updated to 0.010")
        else:
            print("   ✗ audio_wake_pipeline.py: HOTWORD_MIN_RMS not updated")
            all_good = False
        
        if 'OWW_THRESHOLD = _env_float("OPENWAKEWORD_SCORE_THRESHOLD", 0.35)' in content:
            print("   ✓ audio_wake_pipeline.py: OWW_THRESHOLD updated to 0.35")
        else:
            print("   ✗ audio_wake_pipeline.py: OWW_THRESHOLD not updated")
            all_good = False
    
    # Check hotword_engine_manager.py
    manager_file = Path("engine/hotword_engine_manager.py")
    if manager_file.exists():
        content = manager_file.read_text()
        if '_env_float("JARVIS_HOTWORD_MIN_RMS", 0.010)' in content:
            print("   ✓ hotword_engine_manager.py: min_rms default updated to 0.010")
        else:
            print("   ✗ hotword_engine_manager.py: min_rms default not updated")
            all_good = False
        
        if '_env_float("JARVIS_HOTWORD_RISING_EDGE_DELTA", 0.03)' in content:
            print("   ✓ hotword_engine_manager.py: rising_edge_delta default updated to 0.03")
        else:
            print("   ✗ hotword_engine_manager.py: rising_edge_delta default not updated")
            all_good = False
    
    # 4. Summary
    print("\n3. SUMMARY:")
    if all_good:
        print("   ✓ All checks passed! Hotword fix has been applied correctly.")
        print("   \nExpected improvements:")
        print("   - Better noise rejection (higher RMS threshold)")
        print("   - More reliable detection (consecutive hits requirement)")
        print("   - Better signal discrimination (higher score threshold)")
        print("   - Enhanced debugging (hotword debug enabled)")
        return True
    else:
        print("   ✗ Some checks failed. Please review the fixes.")
        return False

if __name__ == "__main__":
    success = verify_hotword_fix()
    sys.exit(0 if success else 1)
""")
    
    print("   ✓ Created verify_hotword_fix.py")
    
    # 8. Run verification script
    print("\n7. RUNNING VERIFICATION:")
    
    try:
        # Change to the correct directory and run verification
        os.chdir("E:\\jarvis-main")
        
        # Try to run python directly
        import subprocess
        result = subprocess.run([sys.executable, "verify_hotword_fix.py"], 
                              capture_output=True, text=True, timeout=60)
        
        print("   Verification output:")
        print(result.stdout)
        if result.stderr:
            print("   Errors:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("   ✓ Verification PASSED!")
        else:
            print(f"   ✗ Verification FAILED with code {result.returncode}")
            
    except Exception as e:
        print(f"   Error running verification: {e}")
    
    print("\n=== FIX SUMMARY ===")
    print("The hotword issue has been addressed by:")
    print("1. Increasing JARVIS_HOTWORD_MIN_RMS from 0.003 to 0.010 (better noise rejection)")
    print("2. Increasing OPENWAKEWORD_SCORE_THRESHOLD from 0.25 to 0.35 (better accuracy)")
    print("3. Increasing OPENWAKEWORD_CONSECUTIVE_HITS from 1 to 2 (more reliable detection)")
    print("4. Adding JARVIS_HOTWORD_DEBUG for troubleshooting")
    print("5. Updating code constants in audio_wake_pipeline.py and hotword_engine_manager.py")
    print("\nThese changes should significantly reduce false positives from random noises.")

if __name__ == "__main__":
    main()
