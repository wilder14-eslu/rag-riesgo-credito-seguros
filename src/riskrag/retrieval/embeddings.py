"""Modelos de embeddings intercambiables.

- ``HashingEmbedder``: local, determinista y sin dependencias (n-gramas de
  caracteres con hashing). Sirve para pruebas, CI y desarrollo sin costo. No
  es semántico de verdad: no sirve para medir la calidad final.
- ``AzureOpenAIEmbedder``: ``text-embedding-3-large`` (o ``-small``) en Azure
  OpenAI, reducido a ``embedding_dim`` dimensiones para que coincida con la
  columna ``VECTOR(1024)`` de pgvector. La elección se hace en la fase 2
  midiendo recall@5.
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal, Protocol

import numpy as np

from riskrag.nlp.normalize import strip_accents

InputType = Literal["document", "query"]


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str], input_type: InputType = "document") -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dim: int = 512, ngram: tuple[int, int] = (3, 5)) -> None:
        self.dim = dim
        self.ngram = ngram

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        norm = f" {strip_accents(text.lower())} "
        words = norm.split()
        feats = list(words)
        for n in range(self.ngram[0], self.ngram[1] + 1):
            feats += [norm[i : i + n] for i in range(max(0, len(norm) - n + 1))]
        for feat in feats:
            h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "little")
            vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        n = np.linalg.norm(vec)
        return vec / n if n else vec

    def embed(self, texts: list[str], input_type: InputType = "document") -> np.ndarray:
        return np.vstack([self._vector(t) for t in texts]) if texts else np.zeros((0, self.dim))


class AzureOpenAIEmbedder:
    """Embeddings de Azure OpenAI. ``client`` se inyecta en las pruebas."""

    batch_size = 64

    def __init__(self, client: Any, deployment: str, dim: int = 1024) -> None:
        self._client = client
        self.deployment = deployment
        self.dim = dim

    def embed(self, texts: list[str], input_type: InputType = "document") -> np.ndarray:
        # Los modelos text-embedding-3 usan el mismo espacio para documentos y consultas
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            resp = self._client.embeddings.create(
                model=self.deployment, input=texts[i : i + self.batch_size], dimensions=self.dim
            )
            vectors += [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
        arr = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / np.where(norms == 0, 1, norms)


def build_embedder(settings: Any, client: Any = None) -> Embedder:
    if settings.embedder_backend == "azure_openai":
        from riskrag.generation.llm import build_azure_openai_client

        return AzureOpenAIEmbedder(
            client or build_azure_openai_client(settings),
            settings.azure_openai_embed_deployment,
            settings.embedding_dim,
        )
    return HashingEmbedder(dim=settings.embedding_dim)
