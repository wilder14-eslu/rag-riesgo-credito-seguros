"""Expansión de consultas con el glosario del dominio.

Las siglas y la jerga (CPP, PD, castigo) suelen no aparecer igual en la
norma. La expansión agrega la forma larga y sinónimos a la consulta léxica
(BM25) sin tocar la consulta que ve el usuario ni la que va al embedding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from riskrag.nlp.normalize import strip_accents


@dataclass
class GlossaryEntry:
    term: str
    definition: str
    synonyms: list[str] = field(default_factory=list)
    source: str | None = None


@lru_cache(maxsize=4)
def load_glossary(path: str) -> dict[str, GlossaryEntry]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out: dict[str, GlossaryEntry] = {}
    for item in raw.get("terminos", []):
        entry = GlossaryEntry(
            term=item["termino"],
            definition=item["definicion"],
            synonyms=item.get("sinonimos", []),
            source=item.get("fuente"),
        )
        for key in [entry.term, *entry.synonyms]:
            out[strip_accents(key.lower())] = entry
    return out


def lookup(term: str, glossary: dict[str, GlossaryEntry]) -> GlossaryEntry | None:
    return glossary.get(strip_accents(term.lower().strip(" ?¿.")))


def expand_query(query: str, glossary: dict[str, GlossaryEntry]) -> str:
    """Devuelve la consulta más los términos equivalentes encontrados."""
    q_norm = f" {strip_accents(query.lower())} "
    extra: list[str] = []
    seen: set[str] = set()
    for key, entry in glossary.items():
        if f" {key} " in q_norm and entry.term not in seen:
            seen.add(entry.term)
            for alt in [entry.term, *entry.synonyms]:
                if strip_accents(alt.lower()) not in q_norm:
                    extra.append(alt)
    return query if not extra else f"{query} {' '.join(extra)}"
