import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_memory_skips_api_key():
    from engine.memory_safety import is_safe_to_store
    safe, reason = is_safe_to_store("my API key is abc123")
    assert safe is False
    assert reason == "secret_or_sensitive"


def test_memory_redacts_secret():
    from engine.memory_safety import redact_sensitive
    assert "[REDACTED]" in redact_sensitive("token=abc123456789")
