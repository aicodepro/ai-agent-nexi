from __future__ import annotations

import sys
import types
from unittest.mock import Mock


def test_router_uses_hashing_embedder_by_default(monkeypatch):
    import engine.router.embedder as embedder

    monkeypatch.delenv("NEXI_ROUTER_EMBEDDER", raising=False)
    heavy = Mock(side_effect=AssertionError("heavy embedder must be opt-in"))
    monkeypatch.setattr(embedder, "SentenceTransformerEmbedder", heavy)

    selected = embedder.get_embedder()

    assert selected.name == "hashing"
    heavy.assert_not_called()


def test_router_e5_embedder_is_explicit_and_cpu_bound(monkeypatch):
    calls = []

    class FakeSentenceTransformer:
        def __init__(self, model, **kwargs):
            calls.append((model, kwargs))

        def get_embedding_dimension(self):
            return 8

    package = types.ModuleType("sentence_transformers")
    package.SentenceTransformer = FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", package)
    monkeypatch.setenv("NEXI_ROUTER_EMBEDDER", "e5")
    monkeypatch.delenv("NEXI_ROUTER_EMBEDDER_DEVICE", raising=False)

    from engine.router.embedder import get_embedder

    selected = get_embedder()

    assert selected.name == "e5-small-v2"
    assert calls == [("intfloat/e5-small-v2", {"device": "cpu"})]


def _fake_openwakeword(monkeypatch, model_type, download):
    package = types.ModuleType("openwakeword")
    model_module = types.ModuleType("openwakeword.model")
    utils_module = types.ModuleType("openwakeword.utils")
    model_module.Model = model_type
    utils_module.download_models = download
    monkeypatch.setitem(sys.modules, "openwakeword", package)
    monkeypatch.setitem(sys.modules, "openwakeword.model", model_module)
    monkeypatch.setitem(sys.modules, "openwakeword.utils", utils_module)


def test_explicit_wake_model_never_triggers_download(monkeypatch, tmp_path):
    download = Mock()

    class FakeModel:
        def __init__(self, **_kwargs):
            self.models = {"hey_nexi": object()}

    _fake_openwakeword(monkeypatch, FakeModel, download)
    model_path = tmp_path / "hey_nexi.onnx"
    model_path.write_bytes(b"model")

    from engine.openwakeword_scorer import OpenWakeWordScorer

    scorer = OpenWakeWordScorer(model_path=str(model_path))

    assert scorer.model_name == "hey_nexi.onnx"
    download.assert_not_called()


def test_wake_scorer_disables_model_after_memory_error(monkeypatch, tmp_path):
    calls = {"predict": 0}

    class FakeModel:
        def __init__(self, **_kwargs):
            self.models = {"hey_nexi": object()}

        def predict(self, _samples):
            calls["predict"] += 1
            raise MemoryError("out of memory")

    _fake_openwakeword(monkeypatch, FakeModel, Mock())
    model_path = tmp_path / "hey_nexi.onnx"
    model_path.write_bytes(b"model")

    from engine.openwakeword_scorer import OpenWakeWordScorer

    scorer = OpenWakeWordScorer(model_path=str(model_path))
    assert scorer.score(b"\x00\x00" * 1280) == 0.0
    assert scorer.score(b"\x00\x00" * 1280) == 0.0

    assert calls["predict"] == 1
    assert scorer.get_debug_snapshot()["load_error"] == "MemoryError: out of memory"
