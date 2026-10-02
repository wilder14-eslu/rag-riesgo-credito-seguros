"""Normalización y tokenización de texto en español para el dominio regulatorio.

La tokenización alimenta BM25: se eliminan tildes solo para la comparación,
se quitan stopwords y se aplica stemming Snowball en español, pero se
preservan los tokens con dígitos (``11356-2008``, ``30``, ``0,70%``) porque
en normativa los números son la parte más informativa de la consulta.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

import snowballstemmer

_STOPWORDS = frozenset(
    """
    a al algo algunas algunos ante antes como con contra cual cuales cuando de del desde donde
    durante e el ella ellas ellos en entre era es esa esas ese eso esos esta estas este esto
    estos fue fueron ha han hasta hay la las le les lo los mas me mi mis mucho muy nada ni no
    nos o otra otras otro otros para pero poco por porque que quien se sea segun ser si sin
    sobre son su sus tambien tanto te tiene tienen todo todos tu un una unas uno unos y ya
    the of and or to in is are for on with by
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-.,/][a-z0-9]+)*%?", re.IGNORECASE)
_WS_RE = re.compile(r"[ \t ]+")


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def clean_text(text: str) -> str:
    """Limpieza conservadora: unifica espacios, guiones raros y saltos de línea."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("‐", "-").replace("‑", "-").replace("–", "-")
    text = text.replace("­", "")  # guion suave de PDFs
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # palabras cortadas por guion de línea
    text = _WS_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@lru_cache(maxsize=1)
def _stemmer() -> snowballstemmer.stemmer:
    return snowballstemmer.stemmer("spanish")


def tokenize(text: str, stem: bool = True) -> list[str]:
    """Tokens para búsqueda léxica (BM25)."""
    norm = strip_accents(text.lower())
    tokens = [t for t in _TOKEN_RE.findall(norm) if t not in _STOPWORDS]
    if not stem:
        return tokens
    stemmer = _stemmer()
    out: list[str] = []
    for tok in tokens:
        if any(ch.isdigit() for ch in tok):
            out.append(tok)
        else:
            out.append(stemmer.stemWord(tok))
    return out


def split_sentences(text: str) -> list[str]:
    """Segmentación de oraciones simple, robusta a abreviaturas comunes en normas."""
    protected = re.sub(r"\b(Art|Res|Num|Inc|Lit|N|Nº|S\.B\.S|Sr|Dr)\.", r"\1<DOT>", text)
    parts = re.split(r"(?<=[.;!?])\s+(?=[A-ZÁÉÍÓÚÑ(\d\[])", protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]
