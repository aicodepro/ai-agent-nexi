"""Tests for double clap gap logic (Phase 5).

Uses the real TzurClapAdapter API.
"""

from engine.tzur_clap_adapter import TzurClapAdapter


def _make_adapter(min_gap_ms=180, max_gap_ms=900):
    return TzurClapAdapter(
        min_clap_gap_ms=min_gap_ms,
        max_clap_gap_ms=max_gap_ms,
    )


def test_double_clap_gap_within_window():
    adapter = _make_adapter()
    adapter._clap_times = [1000.0, 1000.42]
    is_double, gap_ms = adapter._double_clap_gap(1000.5)
    assert is_double is True
    assert gap_ms is not None
    assert 180 <= gap_ms <= 900


def test_double_clap_gap_too_short():
    adapter = _make_adapter()
    adapter._clap_times = [1000.0, 1000.05]
    is_double, gap_ms = adapter._double_clap_gap(1000.1)
    assert is_double is False


def test_double_clap_gap_too_long():
    adapter = _make_adapter()
    adapter._clap_times = [1000.0, 1002.0]
    is_double, gap_ms = adapter._double_clap_gap(1002.1)
    assert is_double is False


def test_single_clap_not_enough():
    adapter = _make_adapter()
    adapter._clap_times = [1000.0]
    is_double, gap_ms = adapter._double_clap_gap(1000.5)
    assert is_double is False


def test_three_claps_uses_first_valid_pair():
    adapter = _make_adapter()
    adapter._clap_times = [1000.0, 1000.5, 1001.0]
    is_double, gap_ms = adapter._double_clap_gap(1001.3)
    assert is_double is True
    assert gap_ms is not None
    assert 180 <= gap_ms <= 900


def test_zero_timestamps_no_wake():
    adapter = _make_adapter()
    adapter._clap_times = [0.0, 0.0]
    is_double, gap_ms = adapter._double_clap_gap(0.5)
    assert is_double is False


def test_gap_measurement_precision():
    adapter = TzurClapAdapter(min_clap_gap_ms=180, max_clap_gap_ms=900)
    adapter._clap_times = [1000.0, 1000.6]
    is_double, gap_ms = adapter._double_clap_gap(1000.7)
    assert is_double is True
    assert gap_ms is not None
    assert abs(gap_ms - 600) < 5
