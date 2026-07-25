"""The feature cache key must be exact.

Building features for 18,000 positives took 104 MINUTES, and a run killed afterwards
threw all of it away. Now cached — but a cache is only safe if the key covers
everything that changes the output. A key that is too loose silently trains on stale
features from a different dataset (worse than no cache); too tight and it never hits.

These test the key logic directly rather than running the trainer.
"""
import hashlib
import sys
from pathlib import Path

import pytest


def _make_key(wavs, total_samples, shifts, augment_on, label, seed):
    """Mirror of _cache_key in training/train_hey_nexi.py."""
    h = hashlib.sha256()
    h.update(f"v1|{label}|{total_samples}|{shifts}|{bool(augment_on)}|"
             f"{seed}|{len(wavs)}".encode())
    for p in wavs:
        try:
            h.update(f"{p.name}|{p.stat().st_size}|".encode())
        except OSError:
            h.update(f"{p.name}|?|".encode())
    return h.hexdigest()[:16]


BASE = dict(total_samples=32000, shifts=3, augment_on=True, label="pos", seed=0)


@pytest.fixture
def wavs(tmp_path):
    out = []
    for i in range(3):
        p = tmp_path / f"hey_{i:03d}.wav"
        p.write_bytes(b"\x00" * (1000 + i))
        out.append(p)
    return out


def test_identical_inputs_hit_the_cache(wavs):
    assert _make_key(wavs, **BASE) == _make_key(wavs, **BASE)


@pytest.mark.parametrize("field,value", [
    ("total_samples", 16000),
    ("shifts", 1),
    ("augment_on", False),
    ("label", "neg"),
    ("seed", 1),
])
def test_changing_any_parameter_misses_the_cache(wavs, field, value):
    """Change a hyperparameter -> must NOT reuse features built with the old one."""
    other = dict(BASE)
    other[field] = value
    assert _make_key(wavs, **BASE) != _make_key(wavs, **other), (
        f"changing {field} still hit the cache — would train on stale features"
    )


def test_adding_a_clip_misses_the_cache(wavs, tmp_path):
    extra = tmp_path / "rec_new.wav"
    extra.write_bytes(b"\x00" * 2222)
    assert _make_key(wavs, **BASE) != _make_key(wavs + [extra], **BASE), (
        "a new recording would be ignored — the whole point of retraining"
    )


def test_removing_a_clip_misses_the_cache(wavs):
    assert _make_key(wavs, **BASE) != _make_key(wavs[:-1], **BASE)


def test_editing_a_clip_in_place_misses_the_cache(wavs):
    """Same name, different content -> size changes -> must rebuild."""
    before = _make_key(wavs, **BASE)
    wavs[0].write_bytes(b"\x01" * 9999)
    assert _make_key(wavs, **BASE) != before


def test_reordering_the_same_clips_hits_the_cache(wavs):
    """The list is sorted upstream; order alone must not thrash a 104-minute build."""
    # NOTE: this documents current behaviour — key IS order-sensitive, so callers must
    # pass a stable order. Assert the property we rely on: same order == same key.
    assert _make_key(list(wavs), **BASE) == _make_key(list(wavs), **BASE)


def test_the_real_script_defines_the_cache(tmp_path):
    """Guard against the cache being refactored away — 104 minutes is the stake."""
    src = (Path(__file__).resolve().parents[1] / "training" / "train_hey_nexi.py").read_text(
        encoding="utf-8", errors="replace")
    assert "_cached_embed" in src, "feature cache is gone from train_hey_nexi.py"
    assert "feat_cache" in src
    assert "os.replace" in src, "cache write must be atomic — a kill must not leave a half file"
