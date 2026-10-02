"""Integración con PostgreSQL + pgvector. Se ejecuta solo si RISKRAG_TEST_PG_DSN está definido."""

import os
from datetime import date

import pytest

DSN = os.getenv("RISKRAG_TEST_PG_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="definir RISKRAG_TEST_PG_DSN para probar pgvector")


def test_pgvector_roundtrip_keeps_metadata_and_filters_expired():
    from riskrag.models import Chunk
    from riskrag.retrieval.embeddings import HashingEmbedder
    from riskrag.retrieval.vector_store import PgVectorStore

    store = PgVectorStore(DSN)
    emb = HashingEmbedder(dim=1024)
    vigente = Chunk(
        chunk_id="t-vig",
        doc_id="t",
        text="provisión genérica vigente",
        domain="riesgo_crediticio",
        effective_from=date(2020, 1, 1),
        source_url="https://www.sbs.gob.pe/x",
    )
    derogado = Chunk(
        chunk_id="t-der",
        doc_id="t",
        text="provisión genérica derogada",
        effective_from=date(2010, 1, 1),
        effective_to=date(2015, 1, 1),
    )
    store.upsert([vigente, derogado], emb.embed([vigente.text, derogado.text]))
    # Re-ingesta: la norma vigente pasa a derogada y el upsert debe guardar la nueva vigencia
    vigente_v2 = vigente.model_copy(update={"effective_to": date(2021, 1, 1)})
    store.upsert([vigente_v2], emb.embed([vigente_v2.text]))

    hits = store.search(emb.embed(["provisión genérica"], "query")[0], k=10, on=date(2026, 1, 1))
    assert all(c.chunk_id not in {"t-vig", "t-der"} for c, _ in hits)
    full = {c.chunk_id: c for c in store.all_chunks()}
    assert full["t-vig"].effective_to == date(2021, 1, 1)
    assert full["t-vig"].source_url == "https://www.sbs.gob.pe/x"
    store.close()
