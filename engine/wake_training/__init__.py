"""NEXI wake-word training-data tooling.

The Voice Data Factory generates diverse "hey nexi" clips from multiple AI voice
sources for training a robust openWakeWord model. See factory.py and
docs/hey-nexi-voice-factory-proposal.md.
"""
from .factory import run, available_sources  # noqa: F401

__all__ = ["run", "available_sources"]
