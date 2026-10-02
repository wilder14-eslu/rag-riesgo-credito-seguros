"""Manifiesto de fuentes aprobadas (defensa contra envenenamiento, OWASP LLM04/LLM08).

Solo se indexan documentos listados en ``configs/fuentes.yaml``: dominio de
origen permitido, metadatos de vigencia y, cuando se conoce, su hash SHA-256.
Un archivo que no está en el manifiesto o cuyo hash cambió no se ingiere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


@dataclass
class ApprovedSource:
    archivo: str
    meta: dict[str, Any] = field(default_factory=dict)
    sha256: str | None = None


@dataclass
class SourceManifest:
    allowed_domains: set[str]
    sources: dict[str, ApprovedSource]

    @classmethod
    def load(cls, path: Path) -> SourceManifest:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        sources = {}
        for item in raw.get("fuentes", []):
            meta = {k: v for k, v in item.items() if k not in {"archivo", "sha256"}}
            sources[item["archivo"]] = ApprovedSource(item["archivo"], meta, item.get("sha256"))
        return cls(set(raw.get("dominios_permitidos", [])), sources)

    def check(self, filename: str, digest: str) -> tuple[bool, str]:
        src = self.sources.get(filename)
        if src is None:
            return False, "no está en el manifiesto de fuentes aprobadas"
        url = src.meta.get("url")
        if url and urlparse(url).hostname not in self.allowed_domains:
            return False, f"dominio no permitido: {urlparse(url).hostname}"
        if src.sha256 and src.sha256 != digest:
            return False, "el hash SHA-256 no coincide con el aprobado"
        return True, "ok"
