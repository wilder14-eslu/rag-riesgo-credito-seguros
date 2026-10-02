"""Detección y enmascarado de datos personales (PII) con foco en Perú.

Se aplica en tres puntos: antes de indexar un documento, antes de registrar
una consulta en los logs y sobre la respuesta final. Las reglas cubren DNI,
RUC, tarjetas (validación Luhn), cuentas CCI, correos y teléfonos. Para
nombres de personas se puede sumar Presidio o Amazon Comprehend (extra ``nlp``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "TARJETA": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "CCI": re.compile(r"\b\d{3}[- ]?\d{3}[- ]?\d{12}[- ]?\d{2}\b"),
    "RUC": re.compile(r"\b(?:10|15|17|20)\d{9}\b"),
    "DNI": re.compile(
        r"(?i)\b(?:dni|documento de identidad|d\.n\.i\.)\s*(?:es|n[°º.]?|nro\.?|numero|número)?\s*[:#]?\s*(\d{8})\b"
    ),
    "TELEFONO": re.compile(r"(?<!\d)(?:\+?51[ -]?)?9\d{2}[ -]?\d{3}[ -]?\d{3}(?!\d)"),
}

# Orden de aplicación: de lo más específico a lo más general
_ORDER = ("EMAIL", "CCI", "TARJETA", "RUC", "DNI", "TELEFONO")


def _luhn_ok(number: str) -> bool:
    digits = [int(d) for d in re.sub(r"\D", "", number)]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


@dataclass(frozen=True)
class PIIFinding:
    kind: str
    start: int
    end: int


def find_pii(text: str) -> list[PIIFinding]:
    findings: list[PIIFinding] = []
    taken: list[tuple[int, int]] = []
    for kind in _ORDER:
        for m in _PATTERNS[kind].finditer(text):
            start, end = (m.start(1), m.end(1)) if kind == "DNI" else (m.start(), m.end())
            if kind == "TARJETA" and not _luhn_ok(m.group()):
                continue
            if any(s < end and start < e for s, e in taken):
                continue
            taken.append((start, end))
            findings.append(PIIFinding(kind, start, end))
    return sorted(findings, key=lambda f: f.start)


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Reemplaza cada dato por ``[TIPO]`` y devuelve los tipos encontrados."""
    findings = find_pii(text)
    if not findings:
        return text, []
    out, last = [], 0
    for f in findings:
        out.append(text[last : f.start])
        out.append(f"[{f.kind}]")
        last = f.end
    out.append(text[last:])
    return "".join(out), sorted({f.kind for f in findings})
