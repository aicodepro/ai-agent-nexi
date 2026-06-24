"""Tests for YAMNet clap backend (optional, graceful when TF not installed)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestYamnetClapBackendOptional:
    def test_imports_without_crashing(self):
        from engine.yamnet_clap_backend import YamnetClapBackend, YamnetClapResult
        assert YamnetClapBackend is not None
        assert YamnetClapResult is not None

    def test_not_ready_when_tf_missing(self):
        from engine.yamnet_clap_backend import YamnetClapBackend
        backend = YamnetClapBackend()
        assert backend.ready is False
        assert "tf_not_installed" in backend._load_error

    def test_process_pcm16_returns_graceful_result_when_not_ready(self):
        from engine.yamnet_clap_backend import YamnetClapBackend
        backend = YamnetClapBackend()
        result = backend.process_pcm16(b"\x00\x00" * 1600)
        assert result.is_clap is False
        assert "not_ready" in result.reason

    def test_get_status_shows_not_ready(self):
        from engine.yamnet_clap_backend import YamnetClapBackend
        backend = YamnetClapBackend()
        status = backend.get_status()
        assert status["ready"] is False
        assert status["backend"] == "yamnet"

    def test_reset_does_not_crash(self):
        from engine.yamnet_clap_backend import YamnetClapBackend
        backend = YamnetClapBackend()
        backend.reset()

    def test_debug_snapshot_returns_status(self):
        from engine.yamnet_clap_backend import YamnetClapBackend
        backend = YamnetClapBackend()
        snap = backend.get_debug_snapshot()
        assert "ready" in snap
        assert "backend" in snap
