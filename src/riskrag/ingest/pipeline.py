"""Pipeline de ingesta: cargar, validar, limpiar, enmascarar, segmentar e indexar."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from riskrag.config import Settings
from riskrag.ingest.legal_chunker import chunk_document
from riskrag.ingest.loaders import load_path
from riskrag.ingest.manifest import SourceManifest
from riskrag.models import Chunk
from riskrag.security.injection import scan
from riskrag.security.pii import mask_pii

logger = logging.getLogger(__name__)

SUPPORTED = {".md", ".txt", ".pdf"}


@dataclass
class IngestReport:
    documents: int = 0
    chunks: int = 0
    rejected: dict[str, str] = field(default_factory=dict)
    quarantined_chunks: list[str] = field(default_factory=list)
    pii_masked: int = 0


def ingest_directory(
    folder: Path, settings: Settings, manifest: SourceManifest | None = None
) -> tuple[list[Chunk], IngestReport]:
    report = IngestReport()
    all_chunks: list[Chunk] = []
    for path in sorted(p for p in folder.rglob("*") if p.suffix.lower() in SUPPORTED):
        meta = None
        if manifest is not None:
            approved = manifest.sources.get(path.name)
            meta = approved.meta if approved else None
        try:
            doc = load_path(path, meta)
        except Exception as exc:  # noqa: BLE001 - se reporta y se sigue
            report.rejected[path.name] = f"error de carga: {exc}"
            continue

        if manifest is not None:
            ok, reason = manifest.check(path.name, doc.sha256 or "")
            if not ok:
                report.rejected[path.name] = reason
                logger.warning("Documento rechazado %s: %s", path.name, reason)
                continue

        masked, kinds = mask_pii(doc.text)
        if kinds:
            report.pii_masked += 1
            doc = doc.model_copy(update={"text": masked})

        report.documents += 1
        for chunk in chunk_document(doc, settings.chunk_max_chars, settings.chunk_overlap_chars):
            injection = scan(chunk.text)
            if injection.is_attack:
                report.quarantined_chunks.append(chunk.chunk_id)
                logger.warning("Chunk en cuarentena %s: %s", chunk.chunk_id, injection.matched)
                continue
            all_chunks.append(chunk)
    report.chunks = len(all_chunks)
    return all_chunks, report
