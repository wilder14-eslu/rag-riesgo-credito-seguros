"""BM25 Okapi sobre tokens normalizados en español.

Implementación propia y pequeña para no depender de librerías externas en
el modo local. Los números de norma y artículo se conservan como tokens, lo
que la búsqueda vectorial suele perder.
"""

from __future__ import annotations

import math
from collections import Counter

from riskrag.nlp.normalize import tokenize


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_ids: list[str] = []
        self._tf: list[Counter[str]] = []
        self._len: list[int] = []
        self._df: Counter[str] = Counter()
        self._avgdl = 0.0

    def fit(self, doc_ids: list[str], texts: list[str]) -> BM25Index:
        self.doc_ids = list(doc_ids)
        self._tf = [Counter(tokenize(t)) for t in texts]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._df = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())
        self._avgdl = (sum(self._len) / len(self._len)) if self._len else 0.0
        return self

    def _idf(self, term: str) -> float:
        n = len(self.doc_ids)
        df = self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = 20) -> list[tuple[str, float]]:
        q_terms = tokenize(query)
        if not q_terms or not self.doc_ids:
            return []
        scores = []
        for i, tf in enumerate(self._tf):
            s = 0.0
            dl = self._len[i] or 1
            for term in q_terms:
                f = tf.get(term, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1))
                    s += self._idf(term) * f * (self.k1 + 1) / denom
            if s > 0:
                scores.append((self.doc_ids[i], s))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]
