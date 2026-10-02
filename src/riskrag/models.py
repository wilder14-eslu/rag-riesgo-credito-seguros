"""Esquemas de datos compartidos por todo el sistema."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class RiskDomain(str, Enum):
    CREDIT = "riesgo_crediticio"
    INSURANCE = "seguros"
    CAPITAL = "capital"
    ACCOUNTING = "contable"
    GENERAL = "general"


class SourceDocument(BaseModel):
    """Documento fuente tal como se ingiere."""

    doc_id: str
    title: str
    text: str
    source_url: str | None = None
    issuer: str | None = None
    norm_id: str | None = Field(None, description="Ej. 'Res. SBS 11356-2008'")
    effective_from: date | None = None
    effective_to: date | None = None
    domain: RiskDomain = RiskDomain.GENERAL
    sha256: str | None = None
    synthetic: bool = Field(False, description="True si es texto de ejemplo, no oficial")


class Chunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    parent_text: str | None = Field(None, description="Contexto ampliado (sección padre)")
    section_path: list[str] = Field(default_factory=list)
    article: str | None = None
    norm_id: str | None = None
    title: str | None = None
    source_url: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    domain: RiskDomain = RiskDomain.GENERAL
    entities: dict[str, list[str]] = Field(default_factory=dict)
    cross_refs: list[str] = Field(default_factory=list)
    synthetic: bool = False

    def is_in_force(self, on: date | None = None) -> bool:
        on = on or date.today()
        if self.effective_from and on < self.effective_from:
            return False
        return not (self.effective_to and on > self.effective_to)

    def citation_label(self) -> str:
        parts = [p for p in (self.norm_id or self.title, self.article) if p]
        return ", ".join(parts) if parts else self.doc_id


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float
    dense_rank: int | None = None
    sparse_rank: int | None = None


class Citation(BaseModel):
    chunk_id: str
    label: str
    source_url: str | None = None


class Answer(BaseModel):
    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    abstained: bool = False
    intent: str | None = None
    unsupported_claims: list[str] = Field(default_factory=list)
    security_flags: list[str] = Field(default_factory=list)
    retrieved_ids: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Respuesta informativa basada en documentos citados. No constituye asesoría legal "
        "ni regulatoria; verifique la versión vigente de cada norma."
    )
