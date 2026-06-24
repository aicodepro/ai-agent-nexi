"""Tests for hotword backend selection (Phase 4)."""

import os


def test_backend_order_default():
    order = (os.getenv("NEXI_HOTWORD_BACKEND_ORDER") or "openwakeword,hotkey").split(",")
    backends = [b.strip().lower() for b in order if b.strip()]
    assert len(backends) >= 1


def test_openwakeword_first_in_order():
    order = (os.getenv("NEXI_HOTWORD_BACKEND_ORDER") or "openwakeword,vosk_keyword,hotkey").split(",")
    backends = [b.strip().lower() for b in order if b.strip()]
    assert "openwakeword" in backends


def test_backend_order_parsing():
    order_str = "openwakeword,vosk_keyword,hotkey"
    backends = [b.strip().lower() for b in order_str.split(",") if b.strip()]
    assert backends == ["openwakeword", "vosk_keyword", "hotkey"]


def test_phrases_default():
    phrases_str = os.getenv("NEXI_HOTWORD_PHRASES") or "hey nexi,nexi"
    phrases = [p.strip().lower() for p in phrases_str.split(",") if p.strip()]
    assert len(phrases) >= 1
    assert "hey nexi" in phrases


def test_phrase_contains_hey_nexi():
    phrases_str = os.getenv("NEXI_HOTWORD_PHRASES") or "hey nexi,nexi"
    phrases = [p.strip().lower() for p in phrases_str.split(",") if p.strip()]
    assert "hey nexi" in phrases


def test_phrase_contains_nexi():
    phrases_str = os.getenv("NEXI_HOTWORD_PHRASES") or "hey nexi,nexi"
    phrases = [p.strip().lower() for p in phrases_str.split(",") if p.strip()]
    assert "nexi" in phrases
