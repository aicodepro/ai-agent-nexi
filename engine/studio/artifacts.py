"""Run-scoped markdown artifacts for the Studio build pipeline."""
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path

# About four characters per token, keeping each handoff close to 500 tokens.
_SOFT_CHAR_CAP = int(os.getenv("NEXI_STUDIO_DOC_CHAR_CAP", "2000"))
_RUN_ID_RE = re.compile(r"^wf_[a-f0-9]{12}$")
_PROJECT_ID_RE = re.compile(r"^proj_[a-f0-9]{20}$")
_PROJECT_DOC_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}\.md$")
_CONTROL_DIR_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
PROJECT_MEMORY_MANIFEST = "manifest.json"
CANONICAL_PROJECT_DOCS = (
    "project-profile.md",
    "decisions.md",
    "architecture-index.md",
    "product-defaults.md",
    "idea-history.md",
)


class ProjectMemoryIntegrityError(ValueError):
    """Raised when canonical project memory does not match its manifest."""


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "project").strip().lower()).strip("-")
    return s or "project"


def build_root() -> Path:
    configured = os.environ.get("NEXI_STUDIO_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "data" / "nexi" / "studio" / "runs").resolve()


def run_dir(run_id: str) -> Path:
    value = str(run_id or "").strip().lower()
    if not _RUN_ID_RE.fullmatch(value):
        raise ValueError("Invalid Studio run ID.")
    return build_root() / value


def projects_root() -> Path:
    configured = os.environ.get("NEXI_STUDIO_PROJECTS_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "data" / "nexi" / "studio" / "projects").resolve()


def project_dir(project_id: str) -> Path:
    value = str(project_id or "").strip()
    if not _PROJECT_ID_RE.fullmatch(value):
        raise ValueError("Invalid Studio project ID.")
    return projects_root() / value


def runtime_control_dir(run_id: str, provider_id: str, task_key: str, agent: str) -> Path:
    """Return a stable per-run/provider/agent cwd separate from the target."""
    value = str(run_id or "").strip().lower()
    if not _RUN_ID_RE.fullmatch(value):
        raise ValueError("Invalid Studio run ID.")
    name = slug(f"{provider_id}-{task_key}-{agent}")[:128]
    if not _CONTROL_DIR_RE.fullmatch(name):
        raise ValueError("Invalid Claude control directory name.")
    configured = os.environ.get("NEXI_STUDIO_CLAUDE_CONTROL_DIR")
    root = Path(configured).expanduser().resolve() if configured else (Path(tempfile.gettempdir()) / "nexi-studio-claude-control").resolve()
    path = root / value / name
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def claude_control_dir(run_id: str, task_key: str, agent: str) -> Path:
    """Compatibility wrapper for existing Claude-specific callers."""
    return runtime_control_dir(run_id, "claude-code", task_key, agent)


def _project_doc_path(project_id: str, filename: str) -> Path:
    name = str(filename or "").strip()
    if not _PROJECT_DOC_RE.fullmatch(name):
        raise ValueError("Invalid Studio project document name.")
    return project_dir(project_id) / name


def write_project_doc(project_id: str, filename: str, content: str) -> dict:
    """Atomically write one canonical project-memory markdown document."""
    path = _project_doc_path(project_id, filename)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    text = str(content or "").strip() + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return {
        "name": path.name,
        "path": str(path),
        "chars": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "created_at": time.time(),
    }


def read_project_doc(project_id: str, filename: str) -> str:
    path = _project_doc_path(project_id, filename)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _project_manifest_path(project_id: str) -> Path:
    return project_dir(project_id) / PROJECT_MEMORY_MANIFEST


def _canonical_project_hashes(project_id: str) -> dict[str, dict]:
    documents: dict[str, dict] = {}
    for name in CANONICAL_PROJECT_DOCS:
        path = _project_doc_path(project_id, name)
        if not path.exists():
            continue
        content = path.read_bytes()
        documents[name] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        }
    return documents


def read_project_manifest(project_id: str) -> dict:
    path = _project_manifest_path(project_id)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectMemoryIntegrityError("Project memory manifest is unreadable.") from exc
    if not isinstance(payload, dict):
        raise ProjectMemoryIntegrityError("Project memory manifest is not an object.")
    return payload


def verify_project_memory(project_id: str) -> dict:
    """Fail closed when canonical project docs drift from the manifest."""
    actual = _canonical_project_hashes(project_id)
    path = _project_manifest_path(project_id)
    if not actual and not path.exists():
        return {"schema_version": 1, "project_id": project_id, "documents": {}, "last_completed_run": None}
    if not path.exists():
        raise ProjectMemoryIntegrityError("Canonical project memory exists without an integrity manifest.")
    manifest = read_project_manifest(project_id)
    if manifest.get("schema_version") != 1 or manifest.get("project_id") != project_id:
        raise ProjectMemoryIntegrityError("Project memory manifest identity or schema is invalid.")
    expected = manifest.get("documents")
    if not isinstance(expected, dict) or set(expected) != set(actual):
        raise ProjectMemoryIntegrityError("Project memory document set does not match the manifest.")
    for name, metadata in expected.items():
        if not isinstance(metadata, dict) or metadata.get("sha256") != actual[name]["sha256"]:
            raise ProjectMemoryIntegrityError(f"Project memory hash mismatch: {name}")
    return manifest


def verify_project_memory_documents(project_id: str, expected_documents: dict[str, dict]) -> dict[str, dict]:
    """Verify an explicitly journaled canonical document set during a resumed write."""
    actual = _canonical_project_hashes(project_id)
    expected = dict(expected_documents or {})
    if set(expected) != set(actual):
        raise ProjectMemoryIntegrityError("Project memory changed outside the journaled write set.")
    for name, metadata in expected.items():
        if not isinstance(metadata, dict) or metadata.get("sha256") != actual[name]["sha256"]:
            raise ProjectMemoryIntegrityError(f"Project memory changed outside the journal: {name}")
    return actual


def publish_project_manifest(
    project_id: str,
    *,
    expected_documents: dict[str, dict] | None = None,
    last_completed_run: str | None = None,
) -> dict:
    """Atomically publish the manifest after all canonical document writes."""
    directory = project_dir(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    documents = _canonical_project_hashes(project_id)
    for name, metadata in dict(expected_documents or {}).items():
        if name not in documents or documents[name]["sha256"] != str(metadata.get("sha256") or ""):
            raise ProjectMemoryIntegrityError(f"Canonical project memory changed before manifest publication: {name}")
    payload = {
        "schema_version": 1,
        "project_id": project_id,
        "documents": documents,
        "last_completed_run": last_completed_run,
        "published_at": time.time(),
    }
    path = _project_manifest_path(project_id)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".manifest.json.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return {
        "name": path.name,
        "path": str(path),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "documents": documents,
        "last_completed_run": last_completed_run,
        "created_at": time.time(),
    }


def _compact(content: str) -> tuple[str, bool]:
    text = str(content or "").strip()
    if len(text) <= _SOFT_CHAR_CAP:
        return text, False
    suffix = "\n\n_[Condensed by Nexi Studio to preserve the handoff budget.]_"
    limit = max(0, _SOFT_CHAR_CAP - len(suffix))
    cut = text.rfind("\n", 0, limit)
    if cut < limit // 2:
        cut = text.rfind(" ", 0, limit)
    if cut < 1:
        cut = limit
    return text[:cut].rstrip() + suffix, True


def write_doc(run_id: str, filename: str, content: str, *, strict: bool = False) -> dict:
    """Atomically write a concise markdown artifact for one workflow run."""
    directory = run_dir(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    filename = os.path.basename(str(filename or "artifact.md"))
    if not filename.endswith(".md"):
        filename += ".md"
    path = directory / filename
    source = str(content or "").strip()
    if strict and len(source) > _SOFT_CHAR_CAP:
        raise ValueError(f"Artifact exceeds the {_SOFT_CHAR_CAP}-character handoff budget.")
    text, truncated = _compact(source)
    fd, temporary = tempfile.mkstemp(prefix=f".{filename}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return {
        "name": filename,
        "path": str(path),
        "chars": len(text),
        "over_cap": truncated,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "created_at": time.time(),
    }


def read_doc(run_id: str, filename: str) -> str:
    if not filename.endswith(".md"):
        filename += ".md"
    path = run_dir(run_id) / os.path.basename(filename)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_run_json(run_id: str, payload: dict) -> dict:
    """Atomically persist the canonical deterministic Studio run state."""
    directory = run_dir(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "run.json"
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".run.json.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return {
        "name": "run.json",
        "path": str(path),
        "chars": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "created_at": time.time(),
    }


def verify_doc(run_id: str, entry: dict) -> bool:
    """Verify one artifact against its recorded content hash."""
    name = os.path.basename(str(entry.get("name") or ""))
    if not name or name == "run.json":
        return False
    content = read_doc(run_id, name)
    return bool(content) and hashlib.sha256(content.encode("utf-8")).hexdigest() == entry.get("sha256")


def list_docs(run_id: str) -> list[str]:
    directory = run_dir(run_id)
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.iterdir() if path.is_file() and path.suffix == ".md")


def cleanup(run_id: str, keep: list[str]) -> list[str]:
    """Delete markdown docs not in `keep` (file hygiene). Returns removed filenames."""
    keep_set = {k if k.endswith(".md") else k + ".md" for k in keep}
    removed = []
    directory = run_dir(run_id)
    for f in list_docs(run_id):
        if f not in keep_set:
            try:
                (directory / f).unlink()
                removed.append(f)
            except OSError:
                pass
    return removed
