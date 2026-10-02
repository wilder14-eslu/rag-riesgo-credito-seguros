"""Recuperación híbrida: denso + BM25 fusionados con Reciprocal Rank Fusion.

RRF combina rankings sin calibrar puntajes de naturaleza distinta
(coseno vs BM25): score(d) = sum(1 / (k + rank_i(d))). Luego se aplica el
filtro de vigencia y el reranker. Si el mejor puntaje final queda bajo
``min_relevance`` el pipeline se abstiene.
"""

from __future__ import annotations

from datetime import date

from riskrag.models import Chunk, RetrievedChunk
from riskrag.retrieval.bm25 import BM25Index
from riskrag.retrieval.embeddings import Embedder
from riskrag.retrieval.reranker import Reranker
from riskrag.retrieval.vector_store import VectorStore


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


class HybridRetriever:
    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        reranker: Reranker,
        top_k_candidates: int = 20,
        top_k_final: int = 5,
        rrf_k: int = 60,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.reranker = reranker
        self.top_k_candidates = top_k_candidates
        self.top_k_final = top_k_final
        self.rrf_k = rrf_k
        self._chunks: dict[str, Chunk] = {}
        self._bm25 = BM25Index()
        self.refresh_lexical_index()

    def refresh_lexical_index(self) -> None:
        chunks = self.store.all_chunks()
        self._chunks = {c.chunk_id: c for c in chunks}
        self._bm25.fit([c.chunk_id for c in chunks], [c.text for c in chunks])

    def retrieve(
        self,
        query: str,
        lexical_query: str | None = None,
        on: date | None = None,
        domain: str | None = None,
    ) -> list[RetrievedChunk]:
        q_vec = self.embedder.embed([query], input_type="query")[0]
        dense = self.store.search(q_vec, self.top_k_candidates, on=on, domain=domain)
        dense_ids = [c.chunk_id for c, _ in dense]
        for c, _ in dense:
            self._chunks[c.chunk_id] = c  # la versión del almacén trae los metadatos al día

        sparse_ids = []
        for cid, _ in self._bm25.search(lexical_query or query, self.top_k_candidates * 2):
            chunk = self._chunks.get(cid)
            if chunk and chunk.is_in_force(on) and (not domain or chunk.domain.value == domain):
                sparse_ids.append(cid)
            if len(sparse_ids) >= self.top_k_candidates:
                break

        fused = reciprocal_rank_fusion([dense_ids, sparse_ids], k=self.rrf_k)
        ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)[: self.top_k_candidates]
        candidates = [
            RetrievedChunk(
                chunk=self._chunks[cid],
                score=score,
                dense_rank=dense_ids.index(cid) + 1 if cid in dense_ids else None,
                sparse_rank=sparse_ids.index(cid) + 1 if cid in sparse_ids else None,
            )
            for cid, score in ordered
        ]
        return self.reranker.rerank(lexical_query or query, candidates, self.top_k_final)
