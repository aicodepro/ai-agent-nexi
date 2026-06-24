import json
import os
import threading
import tempfile
import shutil
from datetime import datetime

_PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)


def _normalize_path(filepath):
    return os.path.abspath(os.path.normpath(filepath))


def _is_inside_project(filepath):
    normalized = _normalize_path(filepath)
    return normalized.startswith(_PROJECT_ROOT + os.sep) or normalized == _PROJECT_ROOT


def validate_storage_path(filepath):
    if not _is_inside_project(filepath):
        return False, f"Path '{filepath}' is outside the project directory"
    return True, ""


class LocalMemoryStore:
    def __init__(self, filepath, _skip_validation=False):
        self._filepath = _normalize_path(filepath)
        if not _skip_validation:
            valid, msg = validate_storage_path(self._filepath)
            if not valid:
                raise ValueError(msg)
        self._lock = threading.Lock()
        self._data = {}
        self._dirty = False
        self._load()

    def _load(self):
        if os.path.exists(self._filepath):
            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                if not isinstance(self._data, dict):
                    self._data = {}
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self):
        dirpath = os.path.dirname(self._filepath)
        if not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            suffix=".json", dir=dirpath,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, self._filepath)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
            self._save()

    def delete(self, key):
        with self._lock:
            existed = key in self._data
            if existed:
                del self._data[key]
                self._save()
            return existed

    def exists(self, key):
        with self._lock:
            return key in self._data

    def keys(self):
        with self._lock:
            return list(self._data.keys())

    def all(self):
        with self._lock:
            return dict(self._data)

    def size(self):
        with self._lock:
            return len(self._data)

    def clear(self):
        with self._lock:
            self._data = {}
            self._save()

    def filepath(self):
        return self._filepath


class LocalJsonlStore:
    def __init__(self, filepath, _skip_validation=False):
        self._filepath = _normalize_path(filepath)
        if not _skip_validation:
            valid, msg = validate_storage_path(self._filepath)
            if not valid:
                raise ValueError(msg)
        self._lock = threading.Lock()

    def append(self, entry):
        with self._lock:
            dirpath = os.path.dirname(self._filepath)
            if not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
            entry["_timestamp"] = datetime.now().isoformat()
            with open(self._filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_all(self):
        entries = []
        if not os.path.exists(self._filepath):
            return entries
        with self._lock:
            with open(self._filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        return entries

    def read_recent(self, limit=20):
        entries = self.read_all()
        return entries[-limit:]

    def size(self):
        if not os.path.exists(self._filepath):
            return 0
        count = 0
        with self._lock:
            with open(self._filepath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1
        return count

    def filepath(self):
        return self._filepath
