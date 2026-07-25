import os
import threading
from pathlib import Path

from engine.control.base import ControlResult, ControlFunction


SAFE_FOLDERS = []
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SEARCH_TIMEOUT_SECONDS = 5.0
_MAX_SEARCH_DIRECTORIES = 1000


def _resolved_path(path):
    return str(Path(path).expanduser().resolve(strict=False))


def _init_safe_folders():
    if SAFE_FOLDERS:
        return
    folders = [
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Downloads",
        _PROJECT_ROOT,
    ]
    SAFE_FOLDERS.extend(
        _resolved_path(folder)
        for folder in folders
        if folder.exists() or folder.parent.is_dir()
    )


def _is_safe_path(path):
    _init_safe_folders()
    abs_path = os.path.normcase(_resolved_path(path))
    for safe in SAFE_FOLDERS:
        try:
            safe_path = os.path.normcase(_resolved_path(safe))
            common = os.path.commonpath([abs_path, safe_path])
            if common == safe_path:
                return True
        except ValueError:
            continue
    return False


def _get_desktop():
    return os.path.expanduser("~\\Desktop")


def _get_documents():
    return os.path.expanduser("~\\Documents")


def _get_downloads():
    return os.path.expanduser("~\\Downloads")


def _resolve_folder(location):
    loc = location.lower().strip() if location else ""
    if loc in ("desktop", "my desktop", "on desktop"):
        return _get_desktop()
    if loc in ("documents", "my documents", "my docs"):
        return _get_documents()
    if loc in ("downloads", "my downloads"):
        return _get_downloads()
    return None


def handle_create_folder(folder_name=None, location=None, **_):
    if not folder_name:
        return ControlResult.failure(
            message="No folder name specified",
            code="MISSING_ENTITY"
        )
    base = _resolve_folder(location) if location else _get_desktop()
    if not base:
        base = _get_desktop()
    path = os.path.join(base, folder_name)
    if not _is_safe_path(path):
        return ControlResult.failure(
            message=f"Path not allowed: {path}",
            code="PATH_NOT_ALLOWED"
        )
    try:
        os.makedirs(path, exist_ok=True)
        return ControlResult.success(
            message=f"Created folder: {folder_name}",
            data={"path": path}
        )
    except Exception as e:
        return ControlResult.failure(
            message=f"Failed to create folder: {folder_name}",
            code="CREATE_FAILED",
            error_message=str(e)
        )


def handle_create_text_file(file_name=None, location=None, content="", **_):
    if not file_name:
        return ControlResult.failure(
            message="No file name specified",
            code="MISSING_ENTITY"
        )
    base = _resolve_folder(location) if location else _get_desktop()
    if not base:
        base = _get_desktop()
    if not file_name.endswith(".txt"):
        file_name += ".txt"
    path = os.path.join(base, file_name)
    if not _is_safe_path(path):
        return ControlResult.failure(
            message=f"Path not allowed: {path}",
            code="PATH_NOT_ALLOWED"
        )
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return ControlResult.success(
            message=f"Created file: {file_name}",
            data={"path": path}
        )
    except Exception as e:
        return ControlResult.failure(
            message=f"Failed to create file: {file_name}",
            code="CREATE_FAILED",
            error_message=str(e)
        )


def handle_open_folder(location=None, **_):
    folder_path = _resolve_folder(location) if location else None
    if not folder_path:
        return ControlResult.failure(
            message=f"Unknown location: {location}",
            code="UNKNOWN_LOCATION"
        )
    if not _is_safe_path(folder_path):
        return ControlResult.failure(
            message=f"Path not allowed: {folder_path}",
            code="PATH_NOT_ALLOWED"
        )
    try:
        os.startfile(folder_path)
        return ControlResult.success(
            message=f"Opened folder: {folder_path}",
            data={"path": folder_path}
        )
    except Exception as e:
        return ControlResult.failure(
            message="Failed to open folder",
            code="OPEN_FAILED",
            error_message=str(e)
        )


def handle_search_files(file_name=None, location=None, timeout_seconds=_SEARCH_TIMEOUT_SECONDS,
                        cancel_event=None, **_):
    if not file_name:
        return ControlResult.failure(
            message="No file name to search for",
            code="MISSING_ENTITY"
        )
    base = _resolve_folder(location) if location else _get_desktop()
    if not base:
        base = _get_desktop()
    if not _is_safe_path(base):
        return ControlResult.failure(
            message=f"Path not allowed: {base}",
            code="PATH_NOT_ALLOWED"
        )
    if cancel_event is not None and cancel_event.is_set():
        return ControlResult.failure(
            message="File search cancelled",
            code="SEARCH_CANCELLED",
        )

    stop_event = cancel_event or threading.Event()
    state = {"results": [], "error": None, "cancelled": False, "truncated": False}

    def scan():
        try:
            for count, (root, dirs, files) in enumerate(os.walk(base), 1):
                if stop_event.is_set():
                    state["cancelled"] = True
                    return
                if count > _MAX_SEARCH_DIRECTORIES:
                    state["truncated"] = True
                    return
                for name in files + dirs:
                    if file_name.lower() in name.lower():
                        state["results"].append(os.path.join(root, name))
                        if len(state["results"]) >= 50:
                            state["truncated"] = True
                            return
        except Exception as exc:
            state["error"] = exc

    worker = threading.Thread(target=scan, daemon=True)
    worker.start()
    worker.join(max(0.0, float(timeout_seconds)))
    if worker.is_alive():
        stop_event.set()
        return ControlResult.failure(
            message="File search timed out",
            code="SEARCH_TIMEOUT",
        )
    if state["cancelled"]:
        return ControlResult.failure(
            message="File search cancelled",
            code="SEARCH_CANCELLED",
        )
    if state["error"] is None:
        results = state["results"]
        return ControlResult.success(
            message=f"Found {len(results)} matches",
            data={"results": results, "truncated": state["truncated"]}
        )
    return ControlResult.failure(
        message="Failed to search files",
        code="SEARCH_FAILED",
        error_message=str(state["error"]),
    )


def handle_copy_file(source=None, destination=None, **_):
    if not source or not destination:
        return ControlResult.failure(
            message="Source and destination required",
            code="MISSING_ENTITY"
        )
    import shutil
    src = os.path.abspath(source)
    dst = os.path.abspath(destination)
    if not _is_safe_path(src) or not _is_safe_path(dst):
        return ControlResult.failure(
            message="Source or destination path not allowed",
            code="PATH_NOT_ALLOWED"
        )
    try:
        shutil.copy2(src, dst)
        return ControlResult.success(
            message=f"Copied {source} to {destination}"
        )
    except Exception as e:
        return ControlResult.failure(
            message="Failed to copy file",
            code="COPY_FAILED",
            error_message=str(e)
        )


def handle_rename_file(source=None, new_name=None, **_):
    if not source or not new_name:
        return ControlResult.failure(
            message="Source and new name required",
            code="MISSING_ENTITY"
        )
    src = os.path.abspath(source)
    parent = os.path.dirname(src)
    dst = os.path.join(parent, new_name)
    if not _is_safe_path(src) or not _is_safe_path(dst):
        return ControlResult.failure(
            message="Path not allowed",
            code="PATH_NOT_ALLOWED"
        )
    try:
        os.rename(src, dst)
        return ControlResult.success(
            message=f"Renamed {os.path.basename(src)} to {new_name}"
        )
    except Exception as e:
        return ControlResult.failure(
            message="Failed to rename file",
            code="RENAME_FAILED",
            error_message=str(e)
        )


def add_safe_folder(folder_path):
    _init_safe_folders()
    abs_path = _resolved_path(folder_path)
    if abs_path not in SAFE_FOLDERS:
        SAFE_FOLDERS.append(abs_path)


def register_file_controls(registry):
    _init_safe_folders()
    registry.register(
        ControlFunction(
            name="create_folder",
            intent="create folder",
            description="Create a new folder in an allowed location",
            risk_level="MEDIUM",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            required_entities=["folder_name"],
            optional_entities=["location"],
            handler=handle_create_folder
        ),
        extra_keywords=["make folder", "new folder", "create directory"]
    )
    registry.register(
        ControlFunction(
            name="create_text_file",
            intent="create text file",
            description="Create a new text file in an allowed location",
            risk_level="MEDIUM",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            required_entities=["file_name"],
            optional_entities=["location", "content"],
            handler=handle_create_text_file
        ),
        extra_keywords=["make file", "new file", "create file", "text file"]
    )
    registry.register(
        ControlFunction(
            name="open_folder",
            intent="open folder",
            description="Open a known folder (Desktop, Downloads, Documents)",
            risk_level="MEDIUM",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            required_entities=["location"],
            handler=handle_open_folder
        ),
        extra_keywords=["open my", "show my", "go to folder"]
    )
    registry.register(
        ControlFunction(
            name="search_files",
            intent="search files by name",
            description="Search for files by name in allowed locations",
            risk_level="MEDIUM",
            privacy_sensitivity="LOW",
            requires_confirmation=False,
            required_entities=["file_name"],
            optional_entities=["location"],
            handler=handle_search_files
        ),
        extra_keywords=["find file", "search file", "look for file"]
    )
    registry.register(
        ControlFunction(
            name="copy_file",
            intent="copy file",
            description="Copy a file to a new location",
            risk_level="HIGH",
            privacy_sensitivity="MEDIUM",
            requires_confirmation=True,
            required_entities=["source", "destination"],
            handler=handle_copy_file
        ),
        extra_keywords=["copy file", "duplicate file"]
    )
    registry.register(
        ControlFunction(
            name="rename_file",
            intent="rename file",
            description="Rename a file",
            risk_level="HIGH",
            privacy_sensitivity="MEDIUM",
            requires_confirmation=True,
            required_entities=["source", "new_name"],
            handler=handle_rename_file
        ),
        extra_keywords=["rename file", "rename to"]
    )
