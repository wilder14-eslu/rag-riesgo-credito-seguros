"""Chunking jerárquico que respeta la estructura de una norma.

Una norma no es prosa continua: tiene títulos, capítulos, artículos o
numerales y anexos. Cortar por número fijo de caracteres separa la regla de
su excepción. Este chunker:

1. Detecta encabezados por nivel (Título > Capítulo/Anexo > Artículo/Numeral >
   Subnumeral).
2. Crea un chunk hijo por sección hoja (lo que se recupera) y conserva el
   texto del padre como contexto (lo que se le da al LLM).
3. Solo si una sección supera ``max_chars`` la divide por oraciones con
   solapamiento.
4. Añade a cada chunk su ruta (``Capítulo II > Numeral 3``), entidades y
   referencias cruzadas.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from riskrag.models import Chunk, SourceDocument
from riskrag.nlp.entities import extract_cross_references, extract_entities
from riskrag.nlp.normalize import split_sentences

_HEADERS: list[tuple[int, re.Pattern[str], str]] = [
    (0, re.compile(r"^\s*(?:#+\s*)?T[ÍI]TULO\s+([IVXLC]+|\d+)\b.*$", re.IGNORECASE), "Título {}"),
    (
        1,
        re.compile(r"^\s*(?:#+\s*)?CAP[ÍI]TULO\s+([IVXLC]+|\d+)\b.*$", re.IGNORECASE),
        "Capítulo {}",
    ),
    (1, re.compile(r"^\s*(?:#+\s*)?ANEXO\s+([IVXLC]+|\d+|[A-Z])\b.*$", re.IGNORECASE), "Anexo {}"),
    (
        2,
        re.compile(r"^\s*(?:#+\s*)?Art[íi]culo\s+(\d+[°º]?)\s*[.:-]?.*$", re.IGNORECASE),
        "Artículo {}",
    ),
    (2, re.compile(r"^\s*(?:#+\s*)?(\d{1,2})\.\s+[A-ZÁÉÍÓÚÑ].*$"), "Numeral {}"),
    (3, re.compile(r"^\s*(?:#+\s*)?(\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\.?\s+\S.*$"), "Numeral {}"),
]


@dataclass
class _Section:
    level: int
    label: str
    heading: str
    lines: list[str] = field(default_factory=list)
    path: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        return "\n".join(self.lines).strip()


def _match_header(line: str) -> tuple[int, str] | None:
    for level, pattern, template in _HEADERS:
        m = pattern.match(line)
        if m:
            return level, template.format(m.group(1).rstrip("°º"))
    return None


def split_sections(text: str) -> list[_Section]:
    sections: list[_Section] = [_Section(level=-1, label="Preámbulo", heading="")]
    stack: list[_Section] = []
    for line in text.splitlines():
        header = _match_header(line)
        if header is None:
            sections[-1].lines.append(line)
            continue
        level, label = header
        while stack and stack[-1].level >= level:
            stack.pop()
        # "2.1" no cuelga de "Numeral 1": si el prefijo no coincide, sube un nivel
        if level == 3 and stack and stack[-1].label.startswith("Numeral "):
            parent_num = stack[-1].label.split(" ", 1)[1]
            if label.split(" ", 1)[1].split(".")[0] != parent_num:
                stack.pop()
        path = [s.label for s in stack] + [label]
        section = _Section(level=level, label=label, heading=line.strip("# ").strip(), path=path)
        section.lines.append(line.strip("# ").strip())
        sections.append(section)
        stack.append(section)
    return [s for s in sections if s.body]


def _windows(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = split_sentences(text)
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        if current and len(current) + len(sent) + 1 > max_chars:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            cut = tail.find(" ")
            current = (tail[cut + 1 :] if cut >= 0 else tail) + " " + sent
        else:
            current = f"{current} {sent}" if current else sent
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _chunk_id(doc_id: str, path: list[str], idx: int, text: str) -> str:
    digest = hashlib.sha1(f"{doc_id}|{'/'.join(path)}|{idx}|{text}".encode()).hexdigest()[:10]  # noqa: S324
    return f"{doc_id}::{idx:04d}::{digest}"


def chunk_document(doc: SourceDocument, max_chars: int = 1800, overlap: int = 200) -> list[Chunk]:
    sections = split_sections(doc.text)
    by_path = {"/".join(s.path): s for s in sections}
    chunks: list[Chunk] = []
    idx = 0
    for section in sections:
        parent = by_path.get("/".join(section.path[:-1])) if len(section.path) > 1 else None
        parent_text = None
        if parent is not None:
            parent_text = f"{' > '.join(parent.path)}: {parent.body[:max_chars]}"
        article = ", ".join(section.path) if section.path else None
        for piece in _windows(section.body, max_chars, overlap):
            prefix = f"[{doc.title}{' > ' + ' > '.join(section.path) if section.path else ''}]"
            text = f"{prefix}\n{piece}"
            chunks.append(
                Chunk(
                    chunk_id=_chunk_id(doc.doc_id, section.path, idx, piece),
                    doc_id=doc.doc_id,
                    text=text,
                    parent_text=parent_text,
                    section_path=section.path,
                    article=article,
                    norm_id=doc.norm_id,
                    title=doc.title,
                    source_url=doc.source_url,
                    effective_from=doc.effective_from,
                    effective_to=doc.effective_to,
                    domain=doc.domain,
                    entities=extract_entities(piece),
                    cross_refs=extract_cross_references(piece),
                    synthetic=doc.synthetic,
                )
            )
            idx += 1
    return chunks
