"""Almacenes vectoriales intercambiables.

- ``InMemoryVectorStore``: local, se persiste en JSON (chunks + vectores).
- ``PgVectorStore``: PostgreSQL con pgvector (Aurora en AWS). Usa el esquema
  de ``sql/001_crear_esquema_pgvector.sql``. Filtra por vigencia en SQL.
- OpenSearch se documenta como alternativa (ADR 0001) y se implementa solo si
  la comparación de la fase 2 lo justifica.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Protocol

import numpy as np

from riskrag.models import Chunk


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None: ...

    def search(
        self, query_vec: np.ndarray, k: int, on: date | None = None, domain: str | None = None
    ) -> list[tuple[Chunk, float]]: ...

    def all_chunks(self) -> list[Chunk]: ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._vectors: np.ndarray | None = None

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        existing = {c.chunk_id: i for i, c in enumerate(self._chunks)}
        new_chunks, new_vecs = [], []
        for chunk, vec in zip(chunks, vectors, strict=True):
            if chunk.chunk_id in existing and self._vectors is not None:
                i = existing[chunk.chunk_id]
                self._chunks[i] = chunk
                self._vectors[i] = vec
            else:
                new_chunks.append(chunk)
                new_vecs.append(vec)
        if new_chunks:
            self._chunks.extend(new_chunks)
            stacked = np.vstack(new_vecs).astype(np.float32)
            self._vectors = (
                stacked if self._vectors is None else np.vstack([self._vectors, stacked])
            )

    def search(
        self, query_vec: np.ndarray, k: int, on: date | None = None, domain: str | None = None
    ) -> list[tuple[Chunk, float]]:
        if self._vectors is None or not self._chunks:
            return []
        sims = self._vectors @ query_vec.astype(np.float32)
        order = np.argsort(-sims)
        out: list[tuple[Chunk, float]] = []
        for i in order:
            chunk = self._chunks[int(i)]
            if not chunk.is_in_force(on):
                continue
            if domain and chunk.domain.value != domain:
                continue
            out.append((chunk, float(sims[int(i)])))
            if len(out) >= k:
                break
        return out

    def all_chunks(self) -> list[Chunk]:
        return list(self._chunks)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "chunks": [c.model_dump(mode="json") for c in self._chunks],
            "vectors": [] if self._vectors is None else self._vectors.round(6).tolist(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> InMemoryVectorStore:
        store = cls()
        payload = json.loads(path.read_text(encoding="utf-8"))
        store._chunks = [Chunk.model_validate(c) for c in payload["chunks"]]
        if payload["vectors"]:
            store._vectors = np.asarray(payload["vectors"], dtype=np.float32)
        return store


_PG_COLUMNS = (
    "chunk_id, doc_id, texto, texto_padre, ruta_seccion, articulo, norma, titulo, url_fuente, "
    "vigente_desde, vigente_hasta, dominio, entidades, referencias, sintetico"
)
_PG_UPDATABLE = (
    "doc_id",
    "texto",
    "texto_padre",
    "ruta_seccion",
    "articulo",
    "norma",
    "titulo",
    "url_fuente",
    "vigente_desde",
    "vigente_hasta",
    "dominio",
    "entidades",
    "referencias",
    "sintetico",
    "embedding",
)

# SQL armado una sola vez con nombres de columna constantes; los valores siempre van como
# parámetros (%s), nunca interpolados.
_UPDATES = ", ".join(f"{col} = EXCLUDED.{col}" for col in _PG_UPDATABLE)
_UPSERT_SQL = (
    f"INSERT INTO rag.chunk ({_PG_COLUMNS}, embedding) "  # noqa: S608
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
    f"ON CONFLICT (chunk_id) DO UPDATE SET {_UPDATES}, fec_actualizacion = now()"
)
_SEARCH_SQL = (
    f"SELECT {_PG_COLUMNS}, 1 - (embedding <=> %s) AS score FROM rag.chunk "  # noqa: S608
    "WHERE (vigente_desde IS NULL OR vigente_desde <= %s) "
    "AND (vigente_hasta IS NULL OR vigente_hasta >= %s) "
    "AND (%s::text IS NULL OR dominio = %s) "
    "ORDER BY embedding <=> %s LIMIT %s"
)
_ALL_SQL = f"SELECT {_PG_COLUMNS} FROM rag.chunk"  # noqa: S608


def _row_to_chunk(r: tuple) -> Chunk:
    return Chunk(
        chunk_id=r[0],
        doc_id=r[1],
        text=r[2],
        parent_text=r[3],
        section_path=r[4] or [],
        article=r[5],
        norm_id=r[6],
        title=r[7],
        source_url=r[8],
        effective_from=r[9],
        effective_to=r[10],
        domain=r[11],
        entities=r[12] or {},
        cross_refs=r[13] or [],
        synthetic=r[14],
    )


class PgVectorStore:
    """Almacén sobre PostgreSQL + pgvector.

    Usa un pool de conexiones que verifica cada conexión antes de entregarla,
    para sobrevivir a reinicios o escalados de Aurora Serverless. Todas las
    consultas son parametrizadas.
    """

    def __init__(self, dsn: str, min_size: int = 1, max_size: int = 5) -> None:
        from pgvector.psycopg import register_vector
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            kwargs={"autocommit": True},
            configure=register_vector,
            check=ConnectionPool.check_connection,
            open=True,
        )

    def close(self) -> None:
        self._pool.close()

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        rows = [
            (
                c.chunk_id,
                c.doc_id,
                c.text,
                c.parent_text,
                c.section_path,
                c.article,
                c.norm_id,
                c.title,
                c.source_url,
                c.effective_from,
                c.effective_to,
                c.domain.value,
                json.dumps(c.entities, ensure_ascii=False),
                c.cross_refs,
                c.synthetic,
                v,
            )
            for c, v in zip(chunks, vectors, strict=True)
        ]
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.executemany(_UPSERT_SQL, rows)

    def search(
        self, query_vec: np.ndarray, k: int, on: date | None = None, domain: str | None = None
    ) -> list[tuple[Chunk, float]]:
        on = on or date.today()
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(_SEARCH_SQL, (query_vec, on, on, domain, domain, query_vec, k))
            rows = cur.fetchall()
        return [(_row_to_chunk(r), float(r[15])) for r in rows]

    def all_chunks(self) -> list[Chunk]:
        """Todos los fragmentos con metadatos completos (vigencia incluida) para BM25."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(_ALL_SQL)
            return [_row_to_chunk(r) for r in cur.fetchall()]
