"""Verificación de fidelidad: ¿cada oración de la respuesta está respaldada?

Dos niveles:

1. ``LexicalSupportVerifier`` (por defecto, sin dependencias): mide cobertura
   de tokens y exige que los números de la oración aparezcan en el fragmento
   citado. Es estricto con cifras, que es donde un error regulatorio es más
   grave.
2. ``NLIVerifier`` (opcional, extra ``nlp``): un modelo de inferencia de
   lenguaje natural multilingüe decide si el fragmento implica la oración.

Las oraciones no respaldadas se reportan en ``Answer.unsupported_claims`` y,
si superan un umbral, el pipeline se abstiene.
"""

from __future__ import annotations

import re
from typing import Protocol

from riskrag.nlp.normalize import split_sentences, tokenize

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


class SupportVerifier(Protocol):
    def unsupported(self, answer: str, evidence: list[str]) -> list[str]: ...


class LexicalSupportVerifier:
    def __init__(self, min_overlap: float = 0.5) -> None:
        self.min_overlap = min_overlap

    @staticmethod
    def _numbers(text: str) -> set[str]:
        return {n.replace(",", ".") for n in _NUM_RE.findall(text)}

    def is_supported(self, sentence: str, evidence: list[str]) -> bool:
        s_tokens = set(tokenize(sentence))
        if len(s_tokens) < 3:
            return True  # oraciones de enlace, no afirmaciones
        s_numbers = self._numbers(re.sub(r"\[[^\]]+\]", "", sentence))
        for ev in evidence:
            e_tokens = set(tokenize(ev))
            overlap = len(s_tokens & e_tokens) / len(s_tokens)
            if overlap >= self.min_overlap and s_numbers <= self._numbers(ev):
                return True
        return False

    def unsupported(self, answer: str, evidence: list[str]) -> list[str]:
        claims = []
        for sentence in claim_sentences(answer):
            if not self.is_supported(sentence, evidence):
                claims.append(sentence)
        return claims


def claim_sentences(answer: str) -> list[str]:
    """Oraciones de la respuesta; una marca de cita [C#] también cierra una afirmación."""
    out: list[str] = []
    for segment in re.split(r"\[C\d+\]", answer):
        out += [s.strip() for s in split_sentences(segment) if s.strip()]
    return out


class NLIVerifier:  # pragma: no cover - requiere modelos pesados
    """Verificador con un modelo NLI de Hugging Face (instalar extra ``nlp``)."""

    def __init__(
        self,
        model_name: str = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
        threshold: float = 0.6,
    ) -> None:
        from transformers import pipeline

        self._clf = pipeline("text-classification", model=model_name, top_k=None)
        self.threshold = threshold

    def unsupported(self, answer: str, evidence: list[str]) -> list[str]:
        claims = []
        for clean in claim_sentences(answer):
            best = 0.0
            for ev in evidence:
                scores = self._clf({"text": ev[:2000], "text_pair": clean})
                entail = next(
                    (s["score"] for s in scores if s["label"].lower().startswith("entail")), 0.0
                )
                best = max(best, entail)
            if best < self.threshold:
                claims.append(clean)
        return claims
