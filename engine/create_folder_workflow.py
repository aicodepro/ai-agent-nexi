# create_folder_workflow.py
# Batch 3: conversational slot-filling for "create folder".
# Pure logic: returns response strings. The caller (engine.command.allCommands)
# is responsible for a single speak() call. No terminal input(), no eel here.
import os
import re
from pathlib import Path

from engine.workflow_state import (
    start_workflow,
    get_workflow,
    update_workflow,
    clear_workflow,
)

WORKFLOW_NAME = "create_folder"

ALLOWED_LOCATIONS = {
    "desktop": "Desktop",
    "documents": "Documents",
    "downloads": "Downloads",
    "pictures": "Pictures",
    "videos": "Videos",
    "music": "Music",
}

ALLOWED_PROMPT = (
    "I can create it on Desktop, Documents, Downloads, Pictures, Videos, "
    "or Music. Where should I create it?"
)

_CANCEL_WORDS = {
    "cancel", "stop", "never mind", "nevermind", "exit", "leave it", "quit",
    "forget it",
}
_YES_WORDS = {
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "do it",
    "go ahead", "haan", "han", "create it", "please do",
}
_NO_WORDS = {"no", "nope", "nah", "don't", "dont", "do not"}

_WINDOWS_RESERVED = (
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_INVALID_CHARS = set('<>:"/\\|?*')

# Leading trigger phrases, longest first so the most specific match wins.
_TRIGGERS = [
    "create a folder named", "create a folder called", "create folder named",
    "create folder called", "make a folder named", "make a folder called",
    "make folder named", "make folder called", "new folder named",
    "new folder called", "create a folder", "create folder", "make a folder",
    "make folder", "new folder", "folder named", "folder called",
]

_LOCATION_SEPS = (" on ", " in ", " inside ", " to ", " at ")


def _norm(text: str) -> str:
    return (text or "").strip().lower().rstrip(".!?").strip()


def is_cancel(text: str) -> bool:
    return _norm(text) in _CANCEL_WORDS


def resolve_location(text: str):
    """Map free text to a canonical location label, or None if unknown."""
    t = _norm(text)
    if not t:
        return None
    words = set(re.findall(r"[a-z]+", t))
    for key, label in ALLOWED_LOCATIONS.items():
        if t == key or key in words:
            return label
    return None


def is_dangerous_location(text: str) -> bool:
    """Reject raw paths / system locations. Allowed locations are bare words."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if any(ch in t for ch in ("\\", "/", ":")):
        return True
    dangerous = (
        "windows", "system32", "program files", "programfiles",
        "system root", "system", "appdata", "root",
    )
    return any(k in t for k in dangerous)


# Saying the command again is a restart, not a name. Live regression: the user
# said "Create a folder" at the name prompt and it was saved as the folder's
# name. The follow-up layer had already flagged it (switch_detected) but the
# workflow validated and stored it anyway.
_COMMAND_NOT_A_NAME = frozenset({
    "create a folder", "create folder", "create a new folder", "create new folder",
    "make a folder", "make folder", "make a new folder", "make new folder",
    "new folder", "folder", "create", "make",
})


def validate_folder_name(name):
    """Return None if valid, else a user-facing rejection message."""
    if name is None:
        return "That's not a valid folder name. What should I name the folder?"
    n = name.strip()
    if not n or n in (".", ".."):
        return "That's not a valid folder name. What should I name the folder?"
    if n.lower().rstrip(".?!") in _COMMAND_NOT_A_NAME:
        return "That's the command, not a name. What should I call the folder?"
    if any(c in _INVALID_CHARS for c in n):
        return "That folder name has characters I can't use. What should I name the folder?"
    base = n.split(".")[0].strip().lower()
    if base in _WINDOWS_RESERVED:
        return "That name is reserved by Windows. What should I name the folder?"
    if len(n) > 200:
        return "That name is too long. What should I name the folder?"
    return None


def _split_name_location(text: str):
    """Split 'Name on Desktop' -> ('Name', 'Desktop'); else (text, None)."""
    if not text:
        return None, None
    low = text.lower()
    seps = list(_LOCATION_SEPS) + ["on ", "in ", "inside ", "to ", "at "]
    seps = sorted(set(seps), key=len, reverse=True)
    for sep in seps:
        idx = low.find(sep)
        while idx != -1:
            after = text[idx + len(sep):].strip()
            label = resolve_location(after)
            if label:
                name = text[:idx].strip()
                return (name or None), label
            idx = low.find(sep, idx + 1)
    if low.startswith(("on ", "in ", "inside ", "to ", "at ")):
        for prefix in ("on ", "in ", "inside ", "to ", "at "):
            if low.startswith(prefix):
                after = text[len(prefix):].strip()
                label = resolve_location(after)
                if label:
                    return None, label
    return (text.strip() or None), None


def parse_create_folder_command(query: str):
    """Extract (folder_name|None, location_label|None) from an initial command."""
    q = (query or "").strip()
    low = q.lower()
    remainder = ""
    for trig in _TRIGGERS:
        idx = low.find(trig)
        if idx != -1:
            remainder = q[idx + len(trig):].strip()
            break
    name, label = _split_name_location(remainder)
    if name == "":
        name = None
    return name, label


def _create_folder(name: str, label: str) -> str:
    """Create the folder under Path.home()/label. Resolved at call time so
    tests that monkeypatch Path.home() / use tmp_path work."""
    try:
        base = Path.home() / label
        target = base / name
        base_resolved = base.resolve()
        target_resolved = target.resolve()
        try:
            common = os.path.commonpath([str(base_resolved), str(target_resolved)])
        except ValueError:
            return "I can't create a folder there."
        if common != str(base_resolved):
            return "I can't create a folder there."
        if target.exists():
            return "That folder already exists."
        target.mkdir(parents=True, exist_ok=False)
        print(f"[WORKFLOW] folder created: {target}")
        return "Done. Folder created."
    except FileExistsError:
        return "That folder already exists."
    except Exception as e:
        print(f"[WORKFLOW] create folder error: {e}")
        return "Sorry, I couldn't create that folder."


#: Every field this workflow can ask for, and the schema that validates it.
#: The folder family is the first migrated onto DialogueContext, per the
#: recommended migration order.
FIELD_SCHEMAS = {"folder_name": "folder_name", "folder_location": "folder_location"}
REQUIRED_FIELDS = ["folder_name", "folder_location"]


def _open_dialogue(field: str, question: str, slots: dict) -> None:
    """Register the question with the one dialogue owner.

    Best-effort: the legacy workflow_state store still drives execution during
    the migration, so a failure here must not break folder creation.
    """
    try:
        from engine import dialogue_context as dc
        from engine.runtime_bridge import current_bridge_session_id
        collected = {k: v for k, v in slots.items() if k in REQUIRED_FIELDS and v}
        ctx = dc.open_dialogue(
            question=question,
            session_id=str(current_bridge_session_id() or ""),
            workflow_id=WORKFLOW_NAME,
            goal="create a folder",
            required_fields=list(REQUIRED_FIELDS),
            expected_response_schema={"fields": dict(FIELD_SCHEMAS), "expecting": field},
            source="workflow",
        )
        for key, value in collected.items():
            ctx.collected_fields[key] = value
    except Exception:
        pass


def _collect(field: str, value) -> None:
    try:
        from engine import dialogue_context as dc
        from engine.runtime_bridge import current_bridge_session_id
        dc.collect_field(field, value, session_id=str(current_bridge_session_id() or ""))
    except Exception:
        pass


# --- Public entrypoints -----------------------------------------------------

def start_create_folder(query: str, pre_slots: dict | None = None) -> str:
    """Start the workflow from an initial 'create folder' command."""
    slots = dict(pre_slots) if pre_slots else {}
    llm_name = slots.get("folder_name")
    llm_label = slots.get("location")
    name = llm_name
    label = llm_label
    if not name:
        name, label = parse_create_folder_command(query)
        if name and validate_folder_name(name) is not None:
            name = None
        if label and not slots.get("location"):
            slots["location"] = label.lower()
            slots["location_label"] = label
    if name and not slots.get("folder_name"):
        slots["folder_name"] = name
    if slots.get("location"):
        new_label = slots["location"]
        new_label_cap = new_label[0].upper() + new_label[1:] if new_label else ""
        if new_label_cap in ALLOWED_LOCATIONS.values() or any(
            k == new_label for k in ALLOWED_LOCATIONS
        ):
            for key, val in ALLOWED_LOCATIONS.items():
                if new_label in (key, key.lower(), val.lower()):
                    slots["location_label"] = val
                    slots["location"] = key
                    break
            else:
                slots["location_label"] = new_label_cap or new_label
                slots["location"] = new_label
        else:
            slots["location_label"] = new_label_cap or new_label
            slots["location"] = new_label

    name = slots.get("folder_name")
    label = slots.get("location_label")

    if name and label:
        start_workflow(WORKFLOW_NAME, "confirm", slots)
        _open_dialogue("confirmation", f"Create {name} on {label}?", slots)
        return f"Create {name} on {label}?"
    if name and not label:
        start_workflow(WORKFLOW_NAME, "ask_location", slots)
        _open_dialogue("folder_location", f"Where should I create {name}?", slots)
        return f"Where should I create {name}?"
    start_workflow(WORKFLOW_NAME, "ask_name", slots)
    _open_dialogue("folder_name", "What should I name the folder?", slots)
    return "What should I name the folder?"


def handle_workflow_reply(reply: str) -> str:
    """Route the next user reply into the active create-folder workflow."""
    wf = get_workflow()
    if not wf or wf.get("name") != WORKFLOW_NAME:
        clear_workflow()
        return "Cancelled."

    if is_cancel(reply):
        clear_workflow()
        return "Cancelled."

    step = wf.get("step")
    slots = dict(wf.get("slots", {}))

    if step == "ask_name":
        return _reply_name(reply, slots)
    if step == "ask_location":
        return _reply_location(reply, slots)
    if step == "confirm":
        return _reply_confirm(reply, slots)

    clear_workflow()
    return "Cancelled."


def _reply_name(reply: str, slots: dict) -> str:
    name = (reply or "").strip()
    err = validate_folder_name(name)
    if err:
        update_workflow(step="ask_name", slots=slots)
        return err
    slots["folder_name"] = name
    print("[WORKFLOW] slot_saved name=folder_name", flush=True)
    _collect("folder_name", name)
    if slots.get("location_label"):
        update_workflow(step="confirm", slots=slots)
        return f"Create {name} on {slots['location_label']}?"
    update_workflow(step="ask_location", slots=slots)
    _open_dialogue("folder_location", f"Where should I create {name}?", slots)
    return f"Where should I create {name}?"


def _reply_location(reply: str, slots: dict) -> str:
    if is_dangerous_location(reply):
        update_workflow(step="ask_location", slots=slots)
        return ALLOWED_PROMPT
    label = resolve_location(reply)
    if not label:
        update_workflow(step="ask_location", slots=slots)
        return ALLOWED_PROMPT
    slots["location"] = label.lower()
    slots["location_label"] = label
    print("[WORKFLOW] slot_saved name=location", flush=True)
    update_workflow(step="confirm", slots=slots)
    return f"Create {slots.get('folder_name', 'the folder')} on {label}?"


def _reply_confirm(reply: str, slots: dict) -> str:
    t = _norm(reply)
    if t in _YES_WORDS:
        name = slots.get("folder_name")
        label = slots.get("location_label")
        if not name or not label:
            clear_workflow()
            return "Cancelled."
        msg = _create_folder(name, label)
        print("[WORKFLOW] executed id=create_folder", flush=True)
        clear_workflow()
        return msg
    if t in _NO_WORDS:
        clear_workflow()
        return "Cancelled."
    update_workflow(step="confirm", slots=slots)
    return (
        f"Please say yes or no. Create {slots.get('folder_name', 'the folder')} "
        f"on {slots.get('location_label', 'Desktop')}?"
    )
