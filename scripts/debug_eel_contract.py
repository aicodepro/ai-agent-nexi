"""Static scan of the Eel JS<->Python contract.

Lists:
  - JS eel.<name>( calls (what JS calls on the Python side)
  - Python @eel.expose functions (what Python exposes to JS)
  - Python eel.<name>( calls (what Python calls on the JS side)
  - JS eel.expose(<name>) definitions (what JS exposes to Python)

Reports mismatches.
"""
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WWW = os.path.join(ROOT, "www")
ENGINE = os.path.join(ROOT, "engine")
SRC = os.path.join(ROOT, "src")

def _scan_files(directory, ext):
    for dirpath, _, filenames in os.walk(directory):
        for f in filenames:
            if f.endswith(ext):
                yield os.path.join(dirpath, f)

def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""

# --- JS side ---
js_calls_python = set()  # eel.<name>( in JS
js_exposes = set()       # eel.expose(<name>) in JS

for path in _scan_files(WWW, ".js"):
    text = _read(path)
    # eel.someName( — JS calling a Python-exposed function
    for m in re.finditer(r'eel\.(\w+)\s*\(', text):
        name = m.group(1)
        if name != "expose" and name != "init" and name != "start":
            js_calls_python.add(name)
    # eel.expose(FuncName) — JS exposing a function to Python
    for m in re.finditer(r'eel\.expose\(\s*(\w+)\s*\)', text):
        js_exposes.add(m.group(1))

# --- Python side ---
py_exposed = set()       # @eel.expose functions
py_calls_js = set()      # eel.<name>( in Python (calling JS)

python_files = list(_scan_files(ENGINE, ".py")) + list(_scan_files(SRC, ".py")) + [os.path.join(ROOT, "main.py")]

for path in python_files:
    text = _read(path)
    # @eel.expose above def
    for m in re.finditer(r'@eel\.expose\s*\n\s*def\s+(\w+)', text):
        py_exposed.add(m.group(1))
    # eel.<name>( — Python calling a JS-exposed function
    for m in re.finditer(r'eel\.(\w+)\s*\(', text):
        name = m.group(1)
        if name not in ("expose", "init", "start", "spawn"):
            py_calls_js.add(name)
    # safe_eel_call("<name>", ...) — also a Python->JS call
    for m in re.finditer(r'(?:safe_eel_call|_safe_eel_call)\(\s*["\'](\w+)["\']', text):
        py_calls_js.add(m.group(1))

print("=" * 60)
print("EEL CONTRACT REPORT")
print("=" * 60)

print(f"\nJS calls Python ({len(js_calls_python)}):")
for n in sorted(js_calls_python):
    tag = "OK" if n in py_exposed else "MISSING @eel.expose"
    print(f"  eel.{n}()  ->  {tag}")

print(f"\nPython @eel.expose ({len(py_exposed)}):")
for n in sorted(py_exposed):
    tag = "called by JS" if n in js_calls_python else "not called by JS"
    print(f"  {n}  ->  {tag}")

print(f"\nPython calls JS ({len(py_calls_js)}):")
for n in sorted(py_calls_js):
    tag = "OK" if n in js_exposes else "MISSING JS expose"
    print(f"  eel.{n}()  ->  {tag}")

print(f"\nJS eel.expose ({len(js_exposes)}):")
for n in sorted(js_exposes):
    tag = "called by Python" if n in py_calls_js else "not called by Python"
    print(f"  {n}  ->  {tag}")

# Mismatches
missing_py = js_calls_python - py_exposed
missing_js = py_calls_js - js_exposes

print(f"\n{'='*60}")
if missing_py:
    print(f"WARNING: JS calls these Python functions but no @eel.expose found:")
    for n in sorted(missing_py):
        print(f"  eel.{n}()")
if missing_js:
    print(f"WARNING: Python calls these JS functions but no JS eel.expose found:")
    for n in sorted(missing_js):
        print(f"  eel.{n}()")
if not missing_py and not missing_js:
    print("ALL CONTRACTS MATCHED")
print("=" * 60)
