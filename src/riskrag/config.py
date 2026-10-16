"""Configuración central del sistema.

Todos los valores se leen de variables de entorno con prefijo ``RISKRAG_``
(o de un archivo ``.env``). Los valores por defecto permiten ejecutar todo en
modo local, sin Azure: embeddings por hashing, índice en memoria y un LLM
extractivo determinista. Para producción se cambian los backends a Azure
OpenAI, Azure AI Content Safety y PostgreSQL con pgvector.
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

    # Backends intercambiables
    embedder_backend: Literal["hashing", "azure_openai"] = "hashing"
    vector_backend: Literal["memory", "pgvector"] = "memory"
    llm_backend: Literal["extractive", "azure_openai"] = "extractive"
    reranker_backend: Literal["lexical", "azure_cohere", "none"] = "lexical"
    guardrail_backend: Literal["local", "azure_content_safety"] = "local"

    # Azure OpenAI. Sin api key se usa la identidad administrada (Microsoft Entra ID)
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: SecretStr | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = "gpt-4.1-mini"
    azure_openai_embed_deployment: str = "text-embedding-3-large"
    azure_openai_send_temperature: bool = Field(
        True, description="Los modelos de razonamiento no aceptan temperature: poner False"
    )
    embedding_dim: int = 1024

    # Azure AI Content Safety (Prompt Shields + moderación de texto)
    azure_content_safety_endpoint: str | None = None
    azure_content_safety_api_key: SecretStr | None = None
    azure_content_safety_api_version: str = "2024-09-01"
    azure_content_safety_max_severity: int = Field(
        2, description="Severidad máxima tolerada (0, 2, 4, 6); por encima se bloquea"
    )

    # Rerank opcional: Cohere Rerank desplegado como modelo serverless en Azure AI Foundry
    azure_rerank_endpoint: str | None = None
    azure_rerank_api_key: SecretStr | None = None
    azure_rerank_model: str = "Cohere-rerank-v3.5"

    # Base vectorial
    pg_dsn: SecretStr | None = None

    # Recuperación
    top_k_candidates: int = 20
    top_k_final: int = 5
    rrf_k: int = 60
    min_relevance: float = Field(
        0.45, description="Umbral de abstención calibrado para el reranker léxico"
    )
    min_relevance_azure_rerank: float = Field(
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
        False, description="Además del archivo, escribir en stdout (Log Analytics)"
    )
    # Microsoft Entra ID: tokens de acceso firmados para clientes de la API
    trust_entra_jwt: bool = Field(False, description="Aceptar tokens Bearer de Microsoft Entra ID")
    entra_tenant_id: str | None = None
    entra_audience: str | None = Field(None, description="Application ID URI o client id de la API")
    entra_required_role: str = "RiskRAG.Query"
    # Azure Front Door: si se define, solo se aceptan solicitudes que traen este X-Azure-FDID
    front_door_id: str | None = None
    home_path: str = Field("/docs", description="A dónde redirige la raíz (la demo usa /demo)")
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
        if self.reranker_backend == "azure_cohere":
            return self.min_relevance_azure_rerank
        return self.min_relevance


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
