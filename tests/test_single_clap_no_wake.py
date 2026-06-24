"""Tests for single clap not waking (Phase 5).

Uses the real TzurClapAdapter and ClapStateMachine APIs.
"""

import time
from engine.tzur_clap_adapter import TzurClapAdapter
from engine.clap_detector import ClapStateMachine


def test_single_clap_tzur_adapter_no_wake():
    adapter = TzurClapAdapter(min_clap_gap_ms=180, max_clap_gap_ms=900)
    adapter._clap_times = [1000.0]
    is_double, gap_ms = adapter._double_clap_gap(1000.5)
    assert is_double is False


def test_single_clap_state_machine():
    sm = ClapStateMachine(clock=time.time)
    assert sm.state == "idle"


def test_two_claps_too_close_not_double():
    adapter = TzurClapAdapter(min_clap_gap_ms=180, max_clap_gap_ms=900)
    adapter._clap_times = [1000.0, 1000.03]
    is_double, gap_ms = adapter._double_clap_gap(1000.1)
    assert is_double is False


def test_one_clap_never_triggers_wake():
    adapter = TzurClapAdapter(min_clap_gap_ms=180, max_clap_gap_ms=900)
    adapter._clap_times = [1000.0]
    is_double, gap_ms = adapter._double_clap_gap(1000.5)
    assert is_double is False


def test_three_events_with_valid_gap():
    adapter = TzurClapAdapter(min_clap_gap_ms=180, max_clap_gap_ms=900)
    adapter._clap_times = [1000.0, 1000.5, 1001.0]
    is_double, gap_ms = adapter._double_clap_gap(1001.3)
    assert is_double is True
