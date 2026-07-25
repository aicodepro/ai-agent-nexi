"""Tier 0b — the local semantic router.

Embeds the exemplar bank once, then matches an utterance by cosine similarity
and returns the best intent per bucket plus the top1-top2 margin. This is the
fast (~tens of ms), offline layer that absorbs phrasing/style variance — the
core of "understand it no matter how I say it".
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .decision import Candidate
from .embedder import Embedder, SentenceTransformerEmbedder, get_embedder
from .exemplars import Exemplar, ExemplarBank


@dataclass
class SemMatch:
    best: Candidate
    margin: float            # best.score - second-best-intent.score
    sim: float               # best.score
    candidates: list[Candidate]  # ranked, one per intent


class SemanticRouter:
    def __init__(self, bank: ExemplarBank, embedder: Embedder | None = None) -> None:
        self.bank = bank
        self.emb = embedder or get_embedder()
        texts = bank.texts()
        # e5 wants exemplars encoded as "passage"; the fallback has no such notion
        if isinstance(self.emb, SentenceTransformerEmbedder):
            self.matrix = self.emb.encode_passages(texts)
        else:
            self.matrix = self.emb.encode(texts)

    def match(self, text: str) -> SemMatch:
        if not text.strip() or self.matrix.shape[0] == 0:
            miss = Candidate("unknown", "unknown", "clarify", 0.0, "low")
            return SemMatch(best=miss, margin=0.0, sim=0.0, candidates=[miss])
        query = self.emb.encode([text])[0]
        sims = self.matrix @ query  # rows are L2-normalized -> dot == cosine
        best_by_intent: dict[str, tuple[float, Exemplar]] = {}
        for entry, score in zip(self.bank.entries, sims):
            score = float(score)
            current = best_by_intent.get(entry.intent)
            if current is None or score > current[0]:
                best_by_intent[entry.intent] = (score, entry)
        ranked = sorted(best_by_intent.values(), key=lambda pair: -pair[0])
        candidates = [
            Candidate(e.intent, e.domain, e.route, score, e.stakes) for score, e in ranked
        ]
        best = candidates[0]
        second = candidates[1].score if len(candidates) > 1 else 0.0
        return SemMatch(best=best, margin=best.score - second, sim=best.score,
                        candidates=candidates)


def _demo() -> None:
    from .exemplars import build_bank

    router = SemanticRouter(build_bank())
    for text, expected in [
        ("open google chrome", "open_app"),
        ("what time is it right now", "tell_time"),
        ("how much battery is left", "get_battery_status"),
    ]:
        m = router.match(text)
        top3 = [c.intent for c in m.candidates[:3]]
        assert expected in top3, f"{text!r} -> {top3} (wanted {expected})"
    print("semantic._demo OK  (embedder:", router.emb.name + ")")


if __name__ == "__main__":
    _demo()
