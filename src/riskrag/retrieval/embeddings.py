"""Modelos de embeddings intercambiables.

- ``HashingEmbedder``: local, determinista y sin dependencias (n-gramas de
  caracteres con hashing). Sirve para pruebas, CI y desarrollo sin costo. No
  es semántico de verdad: no sirve para medir la calidad final.
- ``BedrockEmbedder``: Titan Text Embeddings V2 o Cohere Embed Multilingual
  v3 en Bedrock. La elección se hace en la fase 2 midiendo recall@5.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal, Protocol

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


class BedrockEmbedder:  # pragma: no cover - requiere AWS
    def __init__(self, model_id: str, region: str, dim: int = 1024) -> None:
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=region)
        self.model_id = model_id
        self.dim = dim

    def _invoke(self, body: dict) -> dict:
        resp = self._client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(resp["body"].read())

    def embed(self, texts: list[str], input_type: InputType = "document") -> np.ndarray:
        if self.model_id.startswith("cohere."):
            vectors: list[list[float]] = []
            kind = "search_document" if input_type == "document" else "search_query"
            for i in range(0, len(texts), 96):  # límite de lote de Cohere Embed
                out = self._invoke(
                    {"texts": texts[i : i + 96], "input_type": kind, "truncate": "END"}
                )
                vectors += out["embeddings"]
            arr = np.asarray(vectors, dtype=np.float32)
        else:  # Titan Text Embeddings V2
            arr = np.asarray(
                [
                    self._invoke({"inputText": t, "dimensions": self.dim, "normalize": True})[
                        "embedding"
                    ]
                    for t in texts
                ],
                dtype=np.float32,
            )
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / np.where(norms == 0, 1, norms)


def build_embedder(backend: str, model_id: str, region: str, dim: int) -> Embedder:
    if backend == "bedrock":
        return BedrockEmbedder(model_id, region, dim)
    return HashingEmbedder(dim=dim)
