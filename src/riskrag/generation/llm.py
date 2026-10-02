"""Modelos de lenguaje intercambiables.

- ``ExtractiveLLM``: local y determinista. Elige las oraciones de los
  documentos más parecidas a la pregunta y las cita. No parafrasea, así que
  no alucina: es la línea base para CI y para medir la recuperación aislada.
- ``BedrockLLM``: Claude en Bedrock mediante la API Converse.
"""

from __future__ import annotations

import re
from typing import Protocol

from riskrag.generation.prompts import NOT_FOUND_TOKEN, SYSTEM_PROMPT
from riskrag.nlp.normalize import split_sentences, tokenize

_DOC_RE = re.compile(r'<documento id="(C\d+)"[^>]*>\n(.*?)\n</documento>', re.DOTALL)
_QUESTION_RE = re.compile(r"<pregunta>\n(.*?)\n</pregunta>", re.DOTALL)


class LLM(Protocol):
    def generate(self, system: str, user: str, max_tokens: int, temperature: float) -> str: ...


class ExtractiveLLM:
    def __init__(
        self, max_sentences: int = 3, min_overlap: float = 0.4, relative: float = 0.85
    ) -> None:
        self.max_sentences = max_sentences
        self.min_overlap = min_overlap
        self.relative = relative  # solo oraciones cercanas a la mejor: respuestas enfocadas

    def generate(
        self, system: str, user: str, max_tokens: int = 900, temperature: float = 0.0
    ) -> str:
        q_match = _QUESTION_RE.search(user)
        question = q_match.group(1) if q_match else ""
        q_tokens = set(tokenize(question))
        if not q_tokens:
            return NOT_FOUND_TOKEN
        scored: list[tuple[float, int, int, str, str]] = []
        for order, (key, body) in enumerate(_DOC_RE.findall(user)):
            body = body.split("\n(Contexto de la sección superior:")[0]
            # Fuera la ruta [Título > ...] y los encabezados: solo oraciones con contenido
            lines = [
                ln
                for ln in body.splitlines()
                if ln.strip() and not ln.startswith("[") and not _is_heading(ln)
            ]
            for pos, sent in enumerate(split_sentences(" ".join(lines))):
                s_tokens = set(tokenize(sent))
                if len(s_tokens) < 4:
                    continue
                overlap = len(q_tokens & s_tokens) / len(q_tokens)
                scored.append((overlap, -order, -pos, key, sent.strip()))
        scored.sort(reverse=True)
        if not scored:
            return NOT_FOUND_TOKEN
        cutoff = max(self.min_overlap, self.relative * scored[0][0])
        picked = [s for s in scored if s[0] >= cutoff][: self.max_sentences]
        if not picked:
            return NOT_FOUND_TOKEN
        picked.sort(key=lambda s: (-s[1], -s[2]))  # orden de lectura: documento y posición
        return " ".join(f"{sent} [{key}]" for _, _, _, key, sent in picked)


def _is_heading(line: str) -> bool:
    text = line.strip()
    if len(text) > 120 or text.endswith((".", ":", ";")):
        return False
    letters = [c for c in text if c.isalpha()]
    upper_ratio = sum(c.isupper() for c in letters) / len(letters) if letters else 1.0
    return upper_ratio > 0.6 or bool(re.match(r"^\d+(\.\d+)*\.?\s", text))


class BedrockLLM:  # pragma: no cover - requiere AWS
    def __init__(self, model_id: str, region: str) -> None:
        import boto3

        self._client = boto3.client("bedrock-runtime", region_name=region)
        self.model_id = model_id

    def generate(
        self, system: str, user: str, max_tokens: int = 900, temperature: float = 0.0
    ) -> str:
        resp = self._client.converse(
            modelId=self.model_id,
            system=[{"text": system or SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        parts = resp["output"]["message"]["content"]
        return "".join(p.get("text", "") for p in parts).strip()


def build_llm(backend: str, model_id: str, region: str) -> LLM:
    if backend == "bedrock":
        return BedrockLLM(model_id, region)
    return ExtractiveLLM()
