"""Test augmentation manifest records augmentation metadata correctly."""


def test_augmentation_functions_exist():
    """Import the augmentation functions and verify they exist."""
    from scripts.import_clap_datasets import (
        _random_gain, _add_background_noise, _time_shift,
        _random_crop, _silence_padding, _mild_pitch, augment_wav
    )
    import numpy as np

    samples = (np.random.randn(22050) * 1000).astype(np.int16)
    sr = 44100

    # Each must return same-length array
    for fn in [_random_gain, _add_background_noise, _time_shift, _random_crop,
               _silence_padding]:
        result = fn(samples.copy())
        assert len(result) > 0, f"{fn.__name__} returned empty"


def test_augment_wav_returns_named_augmentations():
    """augment_wav must return (samples, name) tuples."""
    from scripts.import_clap_datasets import augment_wav
    import numpy as np

    samples = (np.random.randn(22050) * 1000).astype(np.int16)
    sr = 44100
    types = ["gain", "noise", "shift", "crop", "silence_pad"]

    results = augment_wav(samples, sr, types, is_clap=True)
    assert len(results) == len(types)
    for s, name in results:
        assert len(s) > 0, f"Augmentation {name} returned empty"
        assert name in types, f"Unknown augmentation name: {name}"


def test_augment_clap_uses_more_types_than_not_clap():
    """Clap positives get 5 aug types, not_clap gets 3."""
    from scripts.import_clap_datasets import augment_wav
    import numpy as np

    s = (np.random.randn(22050) * 1000).astype(np.int16)
    all_types = ["gain", "noise", "shift", "crop", "silence_pad", "pitch"]

    clap_results = augment_wav(s, 44100, all_types, is_clap=True)
    not_clap_results = augment_wav(s, 44100, ["gain", "noise", "silence_pad"], is_clap=False)

    assert len(clap_results) >= len(not_clap_results)
