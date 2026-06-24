import multiprocessing

from wake.pipeline import AudioWakePipeline


def test_not_suppressed_without_event():
    p = AudioWakePipeline(command_queue=None, speaking_event=None)
    assert p._suppressed() is False


def test_suppressed_tracks_event():
    ev = multiprocessing.Event()
    p = AudioWakePipeline(command_queue=None, speaking_event=ev)
    assert p._suppressed() is False
    ev.set()
    assert p._suppressed() is True
    ev.clear()
    assert p._suppressed() is False


def test_tts_set_speaking_event():
    import core.tts as tts
    ev = multiprocessing.Event()
    tts.set_speaking_event(ev)
    assert tts._speaking_event is ev
    tts.set_speaking_event(None)
    assert tts._speaking_event is None
