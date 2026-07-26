"""Undo must name what it reversed, and must refuse to destroy user work.

"Undone." tells a user who cannot see the screen nothing. The journal records
what changed so NEXI can say "I removed the empty Project Alpha folder I created
in your Desktop".

This also proves the journal is WIRED: creating a folder writes an entry. An
undo journal nothing records into is this repository's documented failure mode -
a module that exists and is never reached.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import undo_journal


@pytest.fixture(autouse=True)
def _reset():
    undo_journal.reset_for_tests()
    yield
    undo_journal.reset_for_tests()


# --- the journal itself ------------------------------------------------------

def test_nothing_to_undo_is_said_plainly():
    ok, message = undo_journal.undo_last()
    assert ok is False
    assert "nothing" in message.lower()


def test_undo_names_what_it_reversed():
    undo_journal.register_undo_handler(
        "remove_it", lambda **kw: (True, "I removed the empty Project Alpha folder."))
    undo_journal.record(action="create_folder",
                        description="created Project Alpha on your Desktop",
                        undo_action="remove_it", undo_args={"path": "/x"})

    ok, message = undo_journal.undo_last()
    assert ok is True
    assert "Project Alpha" in message, "undo did not say what it reversed"


def test_an_irreversible_action_is_recorded_but_not_offered():
    undo_journal.record(action="sent_email", description="sent an email", undo_action="")
    assert undo_journal.last_undoable() is None
    ok, message = undo_journal.undo_last()
    assert ok is False


def test_the_same_entry_is_not_undone_twice():
    calls = []
    undo_journal.register_undo_handler("remove_it", lambda **kw: (calls.append(1), (True, "done"))[1])
    undo_journal.record(action="create_folder", description="made a folder",
                        undo_action="remove_it", undo_args={})

    assert undo_journal.undo_last()[0] is True
    assert undo_journal.undo_last()[0] is False, "the same action was undone twice"
    assert len(calls) == 1


def test_an_expired_entry_is_not_offered():
    undo_journal.register_undo_handler("remove_it", lambda **kw: (True, "done"))
    entry = undo_journal.record(action="create_folder", description="made a folder",
                                undo_action="remove_it", undo_args={}, ttl_seconds=1.0)
    entry.expires_at = 0.1  # long past
    assert undo_journal.last_undoable() is None


def test_a_failing_handler_reports_failure_not_success():
    undo_journal.register_undo_handler("boom", lambda **kw: (_ for _ in ()).throw(OSError("nope")))
    undo_journal.record(action="create_folder", description="made a folder",
                        undo_action="boom", undo_args={})
    ok, message = undo_journal.undo_last()
    assert ok is False
    assert "couldn't undo" in message.lower()


# --- wired into the folder family --------------------------------------------

def test_creating_a_folder_records_an_undo_entry(tmp_path, monkeypatch):
    from engine import create_folder_workflow as cfw

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / "Desktop").mkdir()

    result = cfw._create_folder("Project Alpha", "Desktop")
    assert "Project Alpha" in result, "the confirmation did not name the folder"

    entry = undo_journal.last_undoable()
    assert entry is not None, "creating a folder recorded no undo entry"
    assert entry.action == "create_folder"
    assert "Project Alpha" in entry.description


def test_undo_removes_the_folder_it_created(tmp_path, monkeypatch):
    from engine import create_folder_workflow as cfw

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / "Desktop").mkdir()
    cfw._create_folder("Project Alpha", "Desktop")
    created = tmp_path / "Desktop" / "Project Alpha"
    assert created.is_dir()

    ok, message = undo_journal.undo_last()
    assert ok is True
    assert created.exists() is False
    assert "Project Alpha" in message


def test_undo_refuses_to_delete_a_folder_the_user_has_used(tmp_path, monkeypatch):
    """Between creation and "undo that" the user may have put work in it."""
    from engine import create_folder_workflow as cfw

    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / "Desktop").mkdir()
    cfw._create_folder("Project Alpha", "Desktop")
    created = tmp_path / "Desktop" / "Project Alpha"
    (created / "notes.txt").write_text("the user's work", encoding="utf-8")

    ok, message = undo_journal.undo_last()
    assert ok is False, "undo deleted a folder containing the user's work"
    assert created.is_dir()
    assert "isn't empty" in message
