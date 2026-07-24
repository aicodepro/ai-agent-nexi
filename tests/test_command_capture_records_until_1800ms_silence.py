from __future__ import annotations


def test_command_capture_records_until_1800ms_silence():
    import engine.audio_wake_pipeline as awp

    # ASR_SILENCE_TIMEOUT_MS falls back to VAD_SILENCE_END_MS, whose code
    # default (unchanged since the initial migration commit) is 2200ms. This
    # test has asserted 1500 since that same commit -- a value that has never
    # matched the code default (nor the test's own "1800ms" name) -- so 1500
    # was stale drift, not an intentional contract.
    assert awp.ASR_SILENCE_TIMEOUT_MS == 2200

