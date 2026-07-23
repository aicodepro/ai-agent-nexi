import json
import time

import pytest

from engine import world_model


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(world_model, "_STORE", tmp_path / "world_model.json")
    world_model.reset_world(keep_durable=False)
    yield
    world_model.reset_world(keep_durable=False)


def _write_snapshot(payload):
    store = world_model._STORE
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(payload), encoding="utf-8")


def test_dict_fields_merge_instead_of_replacing():
    # An ambient sampler tick must not wipe project facts written by a turn.
    world_model.update_world(environment={"active_app": "Code"})
    world_model.update_world(environment={"cpu_percent": 41})
    assert world_model.get_world()["environment"] == {"active_app": "Code", "cpu_percent": 41}


def test_get_world_returns_a_copy():
    world_model.update_world(working_memory={"project": "nexi"})
    snapshot = world_model.get_world()
    snapshot["working_memory"]["project"] = "tampered"
    assert world_model.get_world()["working_memory"]["project"] == "nexi"


def test_stale_snapshot_drops_volatile_but_keeps_durable(monkeypatch):
    # Reloading a week-old last_action would let Nexi claim it just did something.
    monkeypatch.setenv("NEXI_WORLD_STALE_SECONDS", "60")
    world_model.reset_world(keep_durable=False)
    _write_snapshot({
        "last_action": "delete_files",
        "last_result": "verified",
        "current_step": "awaiting confirmation",
        "environment": {"active_app": "Code"},
        "working_memory": {"project": "nexi"},
        "updated_at": time.time() - 3600,
    })
    world_model._load()

    state = world_model.get_world()
    assert state["last_action"] == ""
    assert state["last_result"] == ""
    assert state["current_step"] == ""
    assert state["environment"] == {"active_app": "Code"}
    assert state["working_memory"] == {"project": "nexi"}


def test_fresh_snapshot_keeps_volatile(monkeypatch):
    monkeypatch.setenv("NEXI_WORLD_STALE_SECONDS", "60")
    world_model.reset_world(keep_durable=False)
    _write_snapshot({
        "last_action": "open_app",
        "last_result": "verified",
        "updated_at": time.time(),
    })
    world_model._load()

    assert world_model.get_world()["last_action"] == "open_app"


def test_prompt_block_empty_when_nothing_known():
    # An empty world must inject nothing into the prompt.
    assert world_model.to_prompt_block() == ""


def test_prompt_block_reports_last_action():
    world_model.update_world(last_action="open_app", last_result="verified")
    assert "open_app -> verified" in world_model.to_prompt_block()


def test_sampler_disabled_by_env(monkeypatch):
    monkeypatch.setenv("NEXI_WORLD_SAMPLER", "0")
    assert world_model.start_world_sampler(interval=1) is False


def test_sampler_is_idempotent(monkeypatch):
    monkeypatch.setenv("NEXI_WORLD_SAMPLER", "1")
    try:
        assert world_model.start_world_sampler(interval=60) is True
        assert world_model.start_world_sampler(interval=60) is False
    finally:
        world_model.stop_world_sampler()


def test_window_titles_can_be_opted_out(monkeypatch):
    import engine.os_awareness as os_awareness

    monkeypatch.setattr(
        os_awareness,
        "get_active_window",
        lambda *a, **k: {"active_app": "Code.exe", "active_title": "secrets.env - Code"},
    )
    monkeypatch.setenv("NEXI_WORLD_SAMPLE_TITLES", "0")
    env = world_model._sample_environment()
    assert env["active_app"] == "Code"
    assert "active_title" not in env

    monkeypatch.setenv("NEXI_WORLD_SAMPLE_TITLES", "1")
    assert world_model._sample_environment()["active_title"] == "secrets.env - Code"


def test_unknown_fields_are_ignored():
    world_model.update_world(definitely_not_a_field="x")
    assert not hasattr(world_model.get_world(), "definitely_not_a_field")
    assert "definitely_not_a_field" not in world_model.get_world()
