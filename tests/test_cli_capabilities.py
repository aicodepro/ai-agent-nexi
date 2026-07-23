"""NEXI's view of its three agent CLIs — discovered, never hardcoded.

Darsh runs claude-code + opencode + hermes and wants NEXI to route each task to the
right one with the right (free-first) model. That requires knowing what each CLI ACTUALLY
contains. Everything here is observed from the filesystem/PATH at call time, so installing
or deleting a skill is reflected on the next scan with no code edit.

Two properties worth pinning:
  * a skill is a DIRECTORY with SKILL.md — a flat foo.md is not loaded (this exact shape
    mismatch silently broke the oh-my-hermes install: 36 files copied, 0 skills loaded);
  * routing never invents a capability — if no installed CLI has the required skill, say
    so instead of silently picking one that cannot do the job.
"""
import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.agent_runtime import cli_capabilities as cc


@pytest.fixture(autouse=True)
def _clear_cache():
    cc._CACHE.clear()
    yield
    cc._CACHE.clear()


def _make_cli(tmp_path, name, skills=(), agents=(), flat_files=()):
    sk = tmp_path / name / "skills"
    ag = tmp_path / name / "agents"
    sk.mkdir(parents=True, exist_ok=True)
    ag.mkdir(parents=True, exist_ok=True)
    for s in skills:
        (sk / s).mkdir(parents=True, exist_ok=True)
        (sk / s / "SKILL.md").write_text(f"---\nname: {s}\n---\n", encoding="utf-8")
    for f in flat_files:                      # the broken shape
        (sk / f"{f}.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    for a in agents:
        (ag / f"{a}.md").write_text("agent", encoding="utf-8")
    return sk, ag


def test_a_skill_is_a_directory_with_skill_md(tmp_path):
    sk, _ = _make_cli(tmp_path, "x", skills=["alpha", "beta"])
    assert cc._scan_skills(sk) == ["alpha", "beta"]


def test_flat_md_files_are_not_counted_as_skills(tmp_path):
    """REGRESSION: oh-my-hermes copied 36 flat .md files and reported success while the
    CLI loaded zero of them. Flat files must never inflate the capability count."""
    sk, _ = _make_cli(tmp_path, "x", skills=["real"], flat_files=["fake1", "fake2"])
    found = cc._scan_skills(sk)
    assert found == ["real"], f"flat .md leaked into skills: {found}"


def test_missing_home_is_empty_not_a_crash(tmp_path):
    assert cc._scan_skills(tmp_path / "nope") == []
    assert cc._scan_agents(None) == []


def test_discovery_reports_counts_consistently(monkeypatch, tmp_path):
    sk, ag = _make_cli(tmp_path, "hermes", skills=["a", "b", "c"], agents=["cto", "qa"])
    monkeypatch.setitem(cc._SKILL_HOMES, "hermes", [str(sk)])
    monkeypatch.setitem(cc._AGENT_HOMES, "hermes", [str(ag)])
    monkeypatch.setattr(cc.shutil, "which", lambda e: "/usr/bin/hermes")

    info = cc.discover_cli("hermes", force=True)
    assert info["installed"] is True
    assert info["skill_count"] == 3 == len(info["skills"])
    assert info["agent_count"] == 2


def test_concurrent_capability_discovery_scans_once(monkeypatch):
    calls = {"n": 0}
    calls_lock = threading.Lock()

    def slow_which(_executable):
        with calls_lock:
            calls["n"] += 1
        time.sleep(0.05)
        return "/bin/tool"

    monkeypatch.setattr(cc.shutil, "which", slow_which)
    start = threading.Barrier(6)
    threads = [threading.Thread(target=lambda: (start.wait(), cc.discover_cli("hermes"))) for _ in range(5)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=2)

    assert calls["n"] == 1


def test_uninstalled_cli_is_reported_not_assumed(monkeypatch):
    monkeypatch.setattr(cc.shutil, "which", lambda e: None)
    info = cc.discover_cli("opencode", force=True)
    assert info["installed"] is False
    assert info["path"] == ""


def test_clis_with_skill_only_lists_installed_ones(monkeypatch, tmp_path):
    sk, ag = _make_cli(tmp_path, "hermes", skills=["ponytail"])
    monkeypatch.setitem(cc._SKILL_HOMES, "hermes", [str(sk)])
    monkeypatch.setitem(cc._AGENT_HOMES, "hermes", [str(ag)])
    # only hermes installed
    monkeypatch.setattr(cc.shutil, "which", lambda e: "/bin/hermes" if e == "hermes" else None)
    cc._CACHE.clear()
    assert cc.clis_with_skill("ponytail") == ["hermes"]
    assert cc.clis_with_skill("does-not-exist") == []


def test_one_cli_runs_every_task(monkeypatch, tmp_path):
    """Darsh picks ONE CLI; it does orchestration, code, test — everything. NEXI must
    NOT spread a job across three CLIs. Only the MODEL TIER changes with task weight."""
    sk_o, ag_o = _make_cli(tmp_path, "opencode", skills=["a"])
    monkeypatch.setitem(cc._SKILL_HOMES, "opencode", [str(sk_o)])
    monkeypatch.setitem(cc._AGENT_HOMES, "opencode", [str(ag_o)])
    monkeypatch.setattr(cc.shutil, "which", lambda e: f"/bin/{e}")
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_PROVIDER", "opencode")
    cc._CACHE.clear()

    kinds = ["orchestration", "code", "test", "quick", "research"]
    chosen = {cc.route_task(k)["cli"] for k in kinds}
    assert chosen == {"opencode"}, f"task work was split across CLIs: {chosen}"


def test_heavy_and_light_get_different_model_tiers(monkeypatch, tmp_path):
    """Real programming gets a strong model; small turns get a cheap/free one."""
    sk_o, ag_o = _make_cli(tmp_path, "opencode", skills=["a"])
    monkeypatch.setitem(cc._SKILL_HOMES, "opencode", [str(sk_o)])
    monkeypatch.setitem(cc._AGENT_HOMES, "opencode", [str(ag_o)])
    monkeypatch.setattr(cc.shutil, "which", lambda e: f"/bin/{e}")
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_PROVIDER", "opencode")
    cc._CACHE.clear()

    assert cc.task_weight("code") == "heavy"
    assert cc.task_weight("quick") == "light"
    assert cc.task_weight("totally-unknown-kind") == "heavy", "unknown work must not cheap out"


def test_missing_skill_on_the_active_cli_is_reported(monkeypatch, tmp_path):
    """Parity means the selected CLI should already have it; if not, say so."""
    sk_o, ag_o = _make_cli(tmp_path, "opencode", skills=["a"])
    monkeypatch.setitem(cc._SKILL_HOMES, "opencode", [str(sk_o)])
    monkeypatch.setitem(cc._AGENT_HOMES, "opencode", [str(ag_o)])
    monkeypatch.setattr(cc.shutil, "which", lambda e: f"/bin/{e}")
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_PROVIDER", "opencode")
    cc._CACHE.clear()

    r = cc.route_task("code", required_skill="not-installed-anywhere")
    assert r["cli"] == "opencode", "must stay on the selected CLI"
    assert "warning" in r


def test_routing_returns_a_model_chain_not_one_model(monkeypatch, tmp_path):
    sk, ag = _make_cli(tmp_path, "opencode", skills=["a"])
    monkeypatch.setitem(cc._SKILL_HOMES, "opencode", [str(sk)])
    monkeypatch.setitem(cc._AGENT_HOMES, "opencode", [str(ag)])
    monkeypatch.setattr(cc.shutil, "which", lambda e: f"/bin/{e}")
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_PROVIDER", "opencode")
    cc._CACHE.clear()

    r = cc.route_task("code")
    assert len(r["models"]) >= 2, "a task must resolve to a fallback chain"
    assert not any("gemini-2.5-flash" in m for m in r["models"])


def test_parity_report_makes_a_break_visible(monkeypatch, tmp_path):
    sk_h, ag_h = _make_cli(tmp_path, "hermes", skills=["a", "b"])
    sk_o, ag_o = _make_cli(tmp_path, "opencode", skills=["a"])      # missing 'b'
    monkeypatch.setitem(cc._SKILL_HOMES, "hermes", [str(sk_h)])
    monkeypatch.setitem(cc._AGENT_HOMES, "hermes", [str(ag_h)])
    monkeypatch.setitem(cc._SKILL_HOMES, "opencode", [str(sk_o)])
    monkeypatch.setitem(cc._AGENT_HOMES, "opencode", [str(ag_o)])
    monkeypatch.setattr(cc.shutil, "which",
                        lambda e: f"/bin/{e}" if e in ("hermes", "opencode") else None)
    cc._CACHE.clear()

    rep = cc.parity_report()
    assert rep["in_sync"] is False
    assert "b" in rep["missing"]["opencode"]
