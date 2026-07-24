import json
import os
import threading
import tempfile
import warnings
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PATH_LOCKS = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _normalize_path(filepath):
    return str(Path(filepath).expanduser().resolve(strict=False))


def lock_for_path(filepath):
    key = os.path.normcase(_normalize_path(filepath))
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def quarantine_corrupt_file(filepath, error):
    path = Path(filepath)
    quarantine = path.with_name(
        f"{path.name}.corrupt-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    )
    message = f"Corrupt memory file quarantined: {path} ({error})"
    try:
        os.replace(path, quarantine)
    except OSError as exc:
        message = f"Corrupt memory file could not be quarantined: {path} ({exc})"
    warnings.warn(message, RuntimeWarning, stacklevel=2)
    return message


def atomic_write_json(filepath, data, *, sort_keys=False):
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=sort_keys)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _is_inside_project(filepath):
    normalized = os.path.normcase(_normalize_path(filepath))
    project = os.path.normcase(str(_PROJECT_ROOT))
    try:
        return os.path.commonpath([normalized, project]) == project
    except ValueError:
        return False


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
        self._lock = lock_for_path(self._filepath)
        self._data = {}
        self._load_error = ""
        self._mtime = 0.0
        with self._lock:
            self._load()

    def _load(self):
        if os.path.exists(self._filepath):
            try:
                mtime = os.path.getmtime(self._filepath)
                if mtime <= self._mtime and self._data:
                    return
                self._mtime = mtime
                with open(self._filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("memory root must be a JSON object")
                self._data = data
                self._load_error = ""
            except (json.JSONDecodeError, OSError, ValueError) as exc:
                self._load_error = quarantine_corrupt_file(self._filepath, exc)
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        atomic_write_json(self._filepath, self._data)
        self._mtime = os.path.getmtime(self._filepath) if os.path.exists(self._filepath) else 0

    def get(self, key, default=None):
        with self._lock:
            self._load()
            return self._data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self._load()
            self._data[key] = value
            self._save()

    def delete(self, key):
        with self._lock:
            self._load()
            existed = key in self._data
            if existed:
                del self._data[key]
                self._save()
            return existed

    def exists(self, key):
        with self._lock:
            self._load()
            return key in self._data

    def keys(self):
        with self._lock:
            self._load()
            return list(self._data.keys())

    def all(self):
        with self._lock:
            self._load()
            return dict(self._data)

    def size(self):
        with self._lock:
            self._load()
            return len(self._data)

    def clear(self):
        with self._lock:
            self._data = {}
            self._save()

    def filepath(self):
        return self._filepath

    @property
    def load_error(self):
        return self._load_error


class LocalJsonlStore:
    def __init__(self, filepath, _skip_validation=False):
        self._filepath = _normalize_path(filepath)
        if not _skip_validation:
            valid, msg = validate_storage_path(self._filepath)
            if not valid:
                raise ValueError(msg)
        self._lock = lock_for_path(self._filepath)
        self._load_error = ""

    def append(self, entry):
        with self._lock:
            dirpath = os.path.dirname(self._filepath)
            if not os.path.exists(dirpath):
                os.makedirs(dirpath, exist_ok=True)
            entry = dict(entry)
            entry["_timestamp"] = datetime.now().isoformat()
            with open(self._filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def read_all(self):
        entries = []
        if not os.path.exists(self._filepath):
            return entries
        with self._lock:
            corrupt_error = None
            with open(self._filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError as exc:
                            corrupt_error = exc
            if corrupt_error is not None:
                self._load_error = quarantine_corrupt_file(self._filepath, corrupt_error)
        return entries

    def read_recent(self, limit=20):
        entries = self.read_all()
        return entries[-limit:]

    def size(self):
        if not os.path.exists(self._filepath):
            return 0
        # Line count is an approximation but avoids reading the entire file
        with open(self._filepath, "r", encoding="utf-8") as f:
            return sum(1 for _ in f)

    def filepath(self):
        return self._filepath

    @property
    def load_error(self):
        return self._load_error
