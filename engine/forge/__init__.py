"""Nexi Forge — self-development loop: generate a tool, test it, gate it, register it.

Original Nexi code (Ada-SI / Hermes are reference patterns only). Phase 1 forges
SAFE (pure-compute) tools end-to-end; risky tools and voice-routing land in later
phases. See docs/superpowers/specs/2026-07-13-nexi-forge-design.md.
"""
from engine.forge.forge_engine import forge_tool

__all__ = ["forge_tool"]
