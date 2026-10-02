"""Configuración central del sistema.

Todos los valores se leen de variables de entorno con prefijo ``RISKRAG_``
(o de un archivo ``.env``). Los valores por defecto permiten ejecutar todo en
modo local, sin AWS: embeddings por hashing, índice en memoria y un LLM
extractivo determinista. Para producción se cambian los backends a Bedrock y
pgvector u OpenSearch.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """Raíz con configs/ y data/.

    En desarrollo (instalación editable) es la carpeta del repositorio. En el
    contenedor el paquete se instala en site-packages, así que se usa
    ``RISKRAG_PROJECT_ROOT`` o el directorio de trabajo.
    """
    env = os.getenv("RISKRAG_PROJECT_ROOT")
    if env:
        return Path(env)
    repo_root = Path(__file__).resolve().parents[2]
    if (repo_root / "configs").is_dir():
        return repo_root
    return Path.cwd()


PROJECT_ROOT = _project_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RISKRAG_", env_file=".env", extra="ignore")

    # Entorno
    env: Literal["local", "dev", "prod"] = "local"
    aws_region: str = "us-east-1"

    # Backends intercambiables
    embedder_backend: Literal["hashing", "bedrock"] = "hashing"
    vector_backend: Literal["memory", "pgvector", "opensearch"] = "memory"
    llm_backend: Literal["extractive", "bedrock"] = "extractive"
    reranker_backend: Literal["lexical", "bedrock", "none"] = "lexical"
    guardrail_backend: Literal["local", "bedrock"] = "local"

    # Modelos de Bedrock (confirmar disponibilidad en la región antes de usar)
    bedrock_llm_model_id: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    bedrock_embed_model_id: str = "amazon.titan-embed-text-v2:0"
    bedrock_rerank_model_id: str = "cohere.rerank-v3-5:0"
    bedrock_guardrail_id: str | None = None
    bedrock_guardrail_version: str = "DRAFT"
    embedding_dim: int = 1024

    # Base vectorial
    pg_dsn: SecretStr | None = None
    opensearch_endpoint: str | None = None
    opensearch_index: str = "riskrag-chunks"

    # Recuperación
    top_k_candidates: int = 20
    top_k_final: int = 5
    rrf_k: int = 60
    min_relevance: float = Field(
        0.45, description="Umbral de abstención calibrado para el reranker léxico"
    )
    min_relevance_bedrock_rerank: float = Field(
        0.20, description="Umbral para Cohere Rerank (otra escala). Recalibrar en la fase 2"
    )

    # Chunking
    chunk_max_chars: int = 1800
    chunk_overlap_chars: int = 200

    # Generación
    max_answer_tokens: int = 900
    temperature: float = 0.0

    # Seguridad
    api_keys_sha256: list[str] = Field(default_factory=list)
    max_query_chars: int = 2000
    rate_limit_per_minute: int = 30
    audit_log_path: Path = PROJECT_ROOT / "logs" / "audit.jsonl"
    audit_stdout: bool = Field(
        False, description="Además del archivo, escribir en stdout (CloudWatch)"
    )
    trust_alb_oidc: bool = Field(False, description="Aceptar la identidad firmada por el ALB")
    alb_arn: str | None = None
    approved_sources_path: Path = PROJECT_ROOT / "configs" / "fuentes.yaml"

    # Integración con la plataforma de riesgo crediticio
    credit_model_url: str | None = None
    credit_model_timeout_s: float = 60.0

    # Rutas de datos
    data_dir: Path = PROJECT_ROOT / "data"
    index_path: Path = PROJECT_ROOT / "data" / "processed" / "index.json"
    glossary_path: Path = PROJECT_ROOT / "configs" / "glosario.yaml"
    provisions_path: Path = (
        PROJECT_ROOT / "configs" / "normativa" / "provisiones_sbs_11356_2008.yaml"
    )

    @property
    def effective_min_relevance(self) -> float:
        if self.reranker_backend == "bedrock":
            return self.min_relevance_bedrock_rerank
        return self.min_relevance


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
