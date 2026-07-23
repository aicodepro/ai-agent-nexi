"""Pluggable text embedder for the semantic layer.

Two implementations, picked automatically by `get_embedder()`:

  * SentenceTransformerEmbedder — opt-in real embeddings (intfloat/e5-small-v2,
    ~130MB, ~16ms/utterance on CPU).
  * HashingEmbedder — default numpy-only embedder (hashed char+word n-grams). No ML
    deps, always available, keeps the router runnable + testable everywhere and
    serves as a genuine offline degradation path. Lexical, not deep-semantic.

The real model plugs in the moment `sentence-transformers` is present; nothing
else in the router changes.
"""
from __future__ import annotations

import hashlib
import os
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Embedder(Protocol):
    name: str
    dim: int

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return an (N, dim) float32 matrix of L2-normalized row vectors."""
        ...


class HashingEmbedder:
    """numpy-only fallback: hashed char(3,4)-gram + word(1,2)-gram bag, L2-normed.

    ponytail: lexical hashing, not learned embeddings. Good enough to run tests
    and match against a rich exemplar bank; the real semantic model replaces it
    on-device via SentenceTransformerEmbedder. Upgrade path = install e5.
    """

    name = "hashing"

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def _bump(self, vec: np.ndarray, token: str, weight: float) -> None:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[h % self.dim] += weight
        vec[(h // self.dim) % self.dim] += weight * 0.5  # 2nd probe cuts collisions

    def _vec(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        padded = f" {text.strip().lower()} "
        for n in (3, 4):
            for i in range(len(padded) - n + 1):
                self._bump(vec, padded[i:i + n], 1.0)
        words = text.lower().split()
        for w in words:
            self._bump(vec, "w:" + w, 2.0)
        for i in range(len(words) - 1):
            self._bump(vec, f"b:{words[i]}_{words[i + 1]}", 1.5)
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._vec(t) for t in texts])


class SentenceTransformerEmbedder:
    """Real embeddings via sentence-transformers (default: e5-small-v2).

    e5 expects a task prefix; we use "query: " for utterances and "passage: " for
    exemplars (the model was trained that way). Both are L2-normalized so a dot
    product is cosine similarity.
    """

    name = "e5-small-v2"

    def __init__(self, model: str = "intfloat/e5-small-v2") -> None:
        from sentence_transformers import SentenceTransformer  # lazy, heavy import

        device = (os.getenv("NEXI_ROUTER_EMBEDDER_DEVICE", "cpu") or "cpu").strip()
        self._model = SentenceTransformer(model, device=device)
        try:  # method renamed in newer sentence-transformers; support both
            self.dim = int(self._model.get_embedding_dimension())
        except AttributeError:
            self.dim = int(self._model.get_sentence_embedding_dimension())

    def _encode(self, texts: list[str], prefix: str) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = self._model.encode(
            [prefix + t for t in texts], normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vecs, dtype=np.float32)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "query: ")

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, "passage: ")


def get_embedder(prefer_model: bool | None = None) -> Embedder:
    """Return the resource-safe embedder; e5 requires an explicit opt-in."""
    if prefer_model is None:
        configured = (os.getenv("NEXI_ROUTER_EMBEDDER", "hashing") or "hashing").strip().lower()
        prefer_model = configured in {"e5", "e5-small-v2", "sentence-transformer", "sentence_transformer"}
    if prefer_model:
        try:
            model = (os.getenv("NEXI_ROUTER_EMBEDDER_MODEL", "intfloat/e5-small-v2") or "intfloat/e5-small-v2").strip()
            return SentenceTransformerEmbedder(model=model)
        except Exception:  # ImportError, model download failure, etc.
            pass
    return HashingEmbedder()


def _demo() -> None:
    emb = HashingEmbedder()
    m = emb.encode(["open chrome", "open the chrome browser", "what is the weather"])
    assert m.shape == (3, emb.dim)
    # same-meaning pair should out-score the unrelated one
    cos = m @ m[0]
    assert cos[1] > cos[2], (cos[1], cos[2])
    assert abs(float(cos[0]) - 1.0) < 1e-4  # self-similarity ~1
    print("embedder._demo OK  (using:", emb.name + ")")


if __name__ == "__main__":
    _demo()
