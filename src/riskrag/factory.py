"""Construcción de componentes a partir de la configuración (inyección de dependencias)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from riskrag.config import Settings, get_settings
from riskrag.generation.answer import RAGPipeline
from riskrag.generation.llm import build_llm
from riskrag.ingest.manifest import SourceManifest
from riskrag.ingest.pipeline import IngestReport, ingest_directory
from riskrag.nlp.query_expansion import load_glossary
from riskrag.retrieval.embeddings import build_embedder
from riskrag.retrieval.hybrid import HybridRetriever
from riskrag.retrieval.reranker import build_reranker
from riskrag.retrieval.vector_store import InMemoryVectorStore, PgVectorStore, VectorStore
from riskrag.security.audit import AuditLogger
from riskrag.security.guardrails import build_guardrail
from riskrag.tools.credit_model import CreditModelClient
from riskrag.tools.regulatory import load_tables

logger = logging.getLogger(__name__)


def build_store(settings: Settings) -> VectorStore:
    if settings.vector_backend == "pgvector":
        if settings.pg_dsn is None:
            raise ValueError("RISKRAG_PG_DSN es obligatorio con vector_backend=pgvector")
        return PgVectorStore(settings.pg_dsn.get_secret_value())
    if settings.vector_backend == "opensearch":
        raise NotImplementedError(
            "OpenSearch se habilita tras la comparación de la fase 2 (ADR 0001)."
        )
    if settings.index_path.exists():
        return InMemoryVectorStore.load(settings.index_path)
    logger.warning("No existe el índice %s; ejecuta 'riskrag ingest'.", settings.index_path)
    return InMemoryVectorStore()


def build_index(
    folder: Path, settings: Settings | None = None, use_manifest: bool = True
) -> IngestReport:
    settings = settings or get_settings()
    manifest = SourceManifest.load(settings.approved_sources_path) if use_manifest else None
    chunks, report = ingest_directory(folder, settings, manifest)
    embedder = build_embedder(
        settings.embedder_backend,
        settings.bedrock_embed_model_id,
        settings.aws_region,
        settings.embedding_dim,
    )
    store = InMemoryVectorStore() if settings.vector_backend == "memory" else build_store(settings)
    if chunks:
        store.upsert(chunks, embedder.embed([c.text for c in chunks], input_type="document"))
    if isinstance(store, InMemoryVectorStore):
        store.save(settings.index_path)
    return report


@dataclass
class Services:
    settings: Settings
    pipeline: RAGPipeline
    retriever: HybridRetriever
    audit: AuditLogger
    tables: dict
    credit_model: CreditModelClient


def build_services(settings: Settings | None = None) -> Services:
    settings = settings or get_settings()
    store = build_store(settings)
    embedder = build_embedder(
        settings.embedder_backend,
        settings.bedrock_embed_model_id,
        settings.aws_region,
        settings.embedding_dim,
    )
    reranker = build_reranker(
        settings.reranker_backend, settings.bedrock_rerank_model_id, settings.aws_region
    )
    retriever = HybridRetriever(
        store, embedder, reranker, settings.top_k_candidates, settings.top_k_final, settings.rrf_k
    )
    audit = AuditLogger(settings.audit_log_path, echo_stdout=settings.audit_stdout)
    pipeline = RAGPipeline(
        retriever=retriever,
        llm=build_llm(settings.llm_backend, settings.bedrock_llm_model_id, settings.aws_region),
        guardrail=build_guardrail(
            settings.guardrail_backend,
            settings.bedrock_guardrail_id,
            settings.bedrock_guardrail_version,
            settings.aws_region,
        ),
        glossary=load_glossary(str(settings.glossary_path)),
        audit=audit,
        min_relevance=settings.effective_min_relevance,
        max_query_chars=settings.max_query_chars,
        max_answer_tokens=settings.max_answer_tokens,
        temperature=settings.temperature,
    )
    return Services(
        settings=settings,
        pipeline=pipeline,
        retriever=retriever,
        audit=audit,
        tables=load_tables(str(settings.provisions_path)),
        credit_model=CreditModelClient(settings.credit_model_url, settings.credit_model_timeout_s),
    )


@lru_cache(maxsize=1)
def get_services() -> Services:
    return build_services()
