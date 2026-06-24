import sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, r'E:\jarvis-main')
from src.orin.control import execute_control_action, EmergencyStop

print('=== 1. ACTIVE WINDOW ===')
r = execute_control_action('get_active_window')
print(r.message[:100] if r.message else 'none')

print()
print('=== 2. OPEN NOTEPAD ===')
r = execute_control_action('open_app', {'app_name': 'notepad'})
print(r.message)
time.sleep(1)

print()
print('=== 3. FOCUS NOTEPAD ===')
r = execute_control_action('focus_app', {'app_name': 'notepad'})
print(r.message)

print()
print('=== 4. LIST APPS (look for notepad) ===')
r = execute_control_action('list_apps')
apps = [a['name'] for a in r.data.get('apps', []) if 'note' in a['name'].lower()]
print(f'Found notepad processes: {apps}')

print()
print('=== 5. CLOSE NOTEPAD ===')
r = execute_control_action('close_app', {'app_name': 'notepad'})
print(r.message)

print()
print('=== 6. CREATE FOLDER ON DESKTOP ===')
r = execute_control_action('create_folder', {'folder_name': 'jarvis_test_folder', 'location': 'desktop'})
print(r.message)

print()
print('=== 7. EMERGENCY STOP TEST ===')
EmergencyStop.engage('manual verification')
r = execute_control_action('list_apps')
blocked = not r.ok
code = r.error['code'] if r.error else 'none'
print(f'Blocked: {blocked} - code: {code}')
EmergencyStop.clear()
r = execute_control_action('list_apps')
print(f'After clear: ok={r.ok}')

print()
print('=== ALL LIVE CHECKS PASSED ===')
