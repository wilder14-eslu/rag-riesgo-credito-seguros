"""Reconocimiento de entidades del dominio (NER basado en reglas).

Es la línea base del NER: reglas de alta precisión para las entidades que
más sirven como metadato y filtro. En la fase 2 se compara contra un modelo
entrenado (por ejemplo spaCy con etiquetas propias) usando F1 sobre
fragmentos anotados a mano; el modelo solo reemplaza a las reglas si las supera.
"""

from __future__ import annotations

import re
from collections import defaultdict

ENTITY_PATTERNS: dict[str, re.Pattern[str]] = {
    "NORMA": re.compile(
        r"\b(?:Resoluci[oó]n|Res\.)\s*(?:S\.?B\.?S\.?)?\s*(?:N[°ºo.]*\s*)?(\d{2,5}\s*-\s*\d{4})",
        re.IGNORECASE,
    ),
    "LEY": re.compile(r"\bLey\s*(?:N[°ºo.]*\s*)?(\d{4,5})", re.IGNORECASE),
    "ARTICULO": re.compile(r"\b(?:Art[ií]culo|Art\.)\s*(\d+[A-Za-z°º]*)", re.IGNORECASE),
    "NUMERAL": re.compile(r"\b(?:Numeral|Num\.)\s*(\d+(?:\.\d+)*)", re.IGNORECASE),
    "CAPITULO": re.compile(r"\bCap[ií]tulo\s+([IVXLC]+|\d+)", re.IGNORECASE),
    "ANEXO": re.compile(r"\bAnexo\s+([IVXLC]+|\d+|[A-Z])\b", re.IGNORECASE),
    "PORCENTAJE": re.compile(r"(\d+(?:[.,]\d+)?)\s*%"),
    "DIAS_ATRASO": re.compile(
        r"\(?(\d+)\)?\s*(?:\([a-záéíóú ]+\)\s*)?d[ií]as(?:\s+calendario)?", re.IGNORECASE
    ),
    "FECHA": re.compile(
        r"\b(\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        r"setiembre|septiembre|octubre|noviembre|diciembre)\s+de\s+\d{4})\b",
        re.IGNORECASE,
    ),
    "CATEGORIA_DEUDOR": re.compile(
        r"\b(Normal|Con Problemas Potenciales|CPP|Deficiente|Dudoso|P[eé]rdida)\b"
    ),
    "TIPO_CREDITO": re.compile(
        r"\bcr[eé]ditos?\s+(?:a\s+)?(corporativos?|grandes empresas|medianas empresas|"
        r"peque[ñn]as empresas|microempresas|de consumo(?: no)?[- ]?revolvente|"
        r"hipotecarios? para vivienda)",
        re.IGNORECASE,
    ),
    "METRICA_RIESGO": re.compile(r"\b(PD|LGD|EAD|ECL|VaR|RWA|IFRS\s?9|IFRS\s?17|NIIF\s?9)\b"),
}

_CATEGORY_CANON = {
    "cpp": "CPP",
    "con problemas potenciales": "CPP",
    "normal": "Normal",
    "deficiente": "Deficiente",
    "dudoso": "Dudoso",
    "perdida": "Pérdida",
    "pérdida": "Pérdida",
}


def _canon(label: str, value: str) -> str:
    value = re.sub(r"\s+", "", value) if label == "NORMA" else value.strip()
    if label == "CATEGORIA_DEUDOR":
        return _CATEGORY_CANON.get(value.lower(), value)
    if label == "TIPO_CREDITO":
        return value.lower()
    return value


def extract_entities(text: str) -> dict[str, list[str]]:
    """Devuelve entidades únicas por tipo, en orden de aparición."""
    found: dict[str, list[str]] = defaultdict(list)
    for label, pattern in ENTITY_PATTERNS.items():
        for match in pattern.finditer(text):
            value = _canon(label, match.group(1))
            if value not in found[label]:
                found[label].append(value)
    return dict(found)


_XREF_RE = re.compile(
    r"\b(?:(?:art[ií]culo|numeral)\s+\d+(?:\.\d+)*|cap[ií]tulo\s+[IVXLC]+)"
    r"(?:\s+del?\s+(?:presente\s+)?(?:Reglamento|Cap[ií]tulo\s+[IVXLC]+))?",
    re.IGNORECASE,
)


def extract_cross_references(text: str) -> list[str]:
    """Referencias internas ('numeral 3 del Capítulo II') para el grafo de citas."""
    refs: list[str] = []
    for m in _XREF_RE.finditer(text):
        ref = re.sub(r"\s+", " ", m.group(0)).strip()
        if ref not in refs:
            refs.append(ref)
    return refs
