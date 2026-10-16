"""Reranking de candidatos.

- ``LexicalReranker``: combina cobertura de términos de la consulta,
  coincidencia exacta de números y la puntuación de fusión. Local y barato.
- ``AzureCohereReranker``: Cohere Rerank 3.5 desplegado como modelo serverless
  en Azure AI Foundry (API ``/v2/rerank`` de Cohere). Es opcional: sin él se
  usa el reranker léxico.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

import httpx

from riskrag.models import RetrievedChunk
from riskrag.nlp.normalize import tokenize

_NUM = re.compile(r"\d+(?:[.,]\d+)?")


class Reranker(Protocol):
    def rerank(
        self, query: str, candidates: list[RetrievedChunk], k: int
    ) -> list[RetrievedChunk]: ...


class NoReranker:
    def rerank(self, query: str, candidates: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
        return candidates[:k]


class LexicalReranker:
    """Puntaje en [0, 1] comparable entre consultas (sirve para decidir abstención).

    La fusión RRF se normaliza por su máximo teórico (primer lugar en ambas
    listas, 2 / (k + 1)), no por el máximo observado: así un candidato mediocre
    no recibe puntaje alto solo por ser el mejor de un mal grupo.
    """

    def __init__(
        self,
        w_fusion: float = 0.3,
        w_coverage: float = 0.6,
        w_numbers: float = 0.1,
        rrf_k: int = 60,
    ) -> None:
        self.w_fusion, self.w_coverage, self.w_numbers = w_fusion, w_coverage, w_numbers
        self.max_fusion = 2.0 / (rrf_k + 1)

    def rerank(self, query: str, candidates: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
        if not candidates:
            return []
        q_tokens = set(tokenize(query))
        q_nums = set(_NUM.findall(query))
        rescored = []
        for c in candidates:
            c_tokens = set(tokenize(c.chunk.text))
            coverage = len(q_tokens & c_tokens) / len(q_tokens) if q_tokens else 0.0
            numbers = (
                (len(q_nums & set(_NUM.findall(c.chunk.text))) / len(q_nums)) if q_nums else 0.0
            )
            fusion = min(1.0, c.score / self.max_fusion)
            score = self.w_fusion * fusion + self.w_coverage * coverage + self.w_numbers * numbers
            rescored.append(c.model_copy(update={"score": round(score, 4)}))
        rescored.sort(key=lambda r: r.score, reverse=True)
        return rescored[:k]


class AzureCohereReranker:
    """Cohere Rerank en Azure AI Foundry. ``http`` se inyecta en las pruebas."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str,
        http: httpx.Client | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self.url = endpoint.rstrip("/") + "/v2/rerank"
        self.model = model
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._http = http or httpx.Client(timeout=timeout_s)

    def rerank(self, query: str, candidates: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
        if not candidates:
            return []
        resp = self._http.post(
            self.url,
            headers=self._headers,
            json={
                "model": self.model,
                "query": query,
                "documents": [c.chunk.text for c in candidates],
                "top_n": min(k, len(candidates)),
            },
        )
        resp.raise_for_status()
        return [
            candidates[r["index"]].model_copy(update={"score": float(r["relevance_score"])})
            for r in resp.json()["results"]
        ]


def build_reranker(settings: Any) -> Reranker:
    if settings.reranker_backend == "azure_cohere":
        if not settings.azure_rerank_endpoint or settings.azure_rerank_api_key is None:
            raise ValueError("El rerank de Azure requiere RISKRAG_AZURE_RERANK_ENDPOINT y su clave")
        return AzureCohereReranker(
            settings.azure_rerank_endpoint,
            settings.azure_rerank_api_key.get_secret_value(),
            settings.azure_rerank_model,
        )
    if settings.reranker_backend == "none":
        return NoReranker()
    return LexicalReranker(rrf_k=settings.rrf_k)
