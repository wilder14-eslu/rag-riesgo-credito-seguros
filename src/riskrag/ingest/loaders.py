"""Carga de documentos: Markdown o texto con front matter YAML, y PDF."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from riskrag.models import RiskDomain, SourceDocument
from riskrag.nlp.normalize import clean_text


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_front_matter(raw: str) -> tuple[dict[str, Any], str]:
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            meta = yaml.safe_load(raw[3:end]) or {}
            return meta, raw[end + 4 :]
    return {}, raw


def _to_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _build(meta: dict[str, Any], text: str, fallback_id: str, digest: str) -> SourceDocument:
    return SourceDocument(
        doc_id=str(meta.get("doc_id", fallback_id)),
        title=str(meta.get("titulo", fallback_id)),
        text=clean_text(text),
        source_url=meta.get("url"),
        issuer=meta.get("emisor"),
        norm_id=meta.get("norma"),
        effective_from=_to_date(meta.get("vigente_desde")),
        effective_to=_to_date(meta.get("vigente_hasta")),
        domain=RiskDomain(meta.get("dominio", RiskDomain.GENERAL.value)),
        sha256=digest,
        synthetic=bool(meta.get("sintetico", False)),
    )


def load_text_file(path: Path) -> SourceDocument:
    data = path.read_bytes()
    meta, body = _parse_front_matter(data.decode("utf-8"))
    return _build(meta, body, path.stem, _sha256(data))


def load_pdf(path: Path, meta: dict[str, Any] | None = None) -> SourceDocument:
    from pypdf import PdfReader  # extra "pdf"

    data = path.read_bytes()
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return _build(meta or {}, "\n".join(pages), path.stem, _sha256(data))


def load_path(path: Path, meta: dict[str, Any] | None = None) -> SourceDocument:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return load_text_file(path)
    if suffix == ".pdf":
        return load_pdf(path, meta)
    raise ValueError(f"Formato no soportado: {path.name}")
