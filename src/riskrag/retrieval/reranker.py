"""Reranking de candidatos.

- ``LexicalReranker``: combina cobertura de términos de la consulta,
  coincidencia exacta de números y la puntuación de fusión. Local y barato.
- ``BedrockReranker``: Cohere Rerank 3.5 vía la API ``Rerank`` de
  ``bedrock-agent-runtime``.
"""

from __future__ import annotations

import re
from typing import Protocol

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


class BedrockReranker:  # pragma: no cover - requiere AWS
    def __init__(self, model_id: str, region: str) -> None:
        import boto3

        self._client = boto3.client("bedrock-agent-runtime", region_name=region)
        self.model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"

    def rerank(self, query: str, candidates: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
        if not candidates:
            return []
        resp = self._client.rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": query}}],
            sources=[
                {
                    "type": "INLINE",
                    "inlineDocumentSource": {
                        "type": "TEXT",
                        "textDocument": {"text": c.chunk.text},
                    },
                }
                for c in candidates
            ],
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "numberOfResults": min(k, len(candidates)),
                    "modelConfiguration": {"modelArn": self.model_arn},
                },
            },
        )
        return [
            candidates[r["index"]].model_copy(update={"score": float(r["relevanceScore"])})
            for r in resp["results"]
        ]


def build_reranker(backend: str, model_id: str, region: str) -> Reranker:
    if backend == "bedrock":
        return BedrockReranker(model_id, region)
    if backend == "none":
        return NoReranker()
    return LexicalReranker()
