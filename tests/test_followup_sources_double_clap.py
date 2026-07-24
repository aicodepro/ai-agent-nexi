"""Guard: the clap wake path emits source 'double_clap' (clap_backend_manager.py:247,
audio_wake_pipeline.py normalizes clap/double-clap -> 'double_clap'). If that source is
not in _FOLLOWUP_SOURCES, auto-followup silently dies after any question asked during a
clap-initiated turn. This pins the fix so it can't be 'cleaned up' away again.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_double_clap_is_a_followup_source():
    from engine.command import _FOLLOWUP_SOURCES
    assert "double_clap" in _FOLLOWUP_SOURCES, (
        "clap wake emits source 'double_clap'; it must be allowed to auto-followup"
    )
    # the plain 'clap' alias is effectively dead for the wake path, but keep it allowed too
    assert "clap" in _FOLLOWUP_SOURCES
