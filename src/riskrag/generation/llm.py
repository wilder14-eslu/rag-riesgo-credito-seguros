"""Modelos de lenguaje intercambiables.

- ``ExtractiveLLM``: local y determinista. Elige las oraciones de los
  documentos más parecidas a la pregunta y las cita. No parafrasea, así que
  no alucina: es la línea base para CI y para medir la recuperación aislada.
- ``AzureOpenAILLM``: un modelo GPT desplegado en Azure OpenAI (Chat Completions),
  autenticado con identidad administrada de Microsoft Entra ID.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol

from riskrag.generation.prompts import NOT_FOUND_TOKEN, SYSTEM_PROMPT
from riskrag.nlp.normalize import split_sentences, tokenize

if TYPE_CHECKING:
    from riskrag.config import Settings

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


def build_azure_openai_client(settings: Settings) -> Any:  # pragma: no cover - requiere Azure
    from openai import AzureOpenAI

    from riskrag.azure_auth import token_provider

    if not settings.azure_openai_endpoint:
        raise ValueError(
            "RISKRAG_AZURE_OPENAI_ENDPOINT es obligatorio con backends de Azure OpenAI"
        )
    if settings.azure_openai_api_key is not None:
        return AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
            api_key=settings.azure_openai_api_key.get_secret_value(),
        )
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=token_provider(),
    )


class AzureOpenAILLM:
    """Chat Completions de Azure OpenAI. ``client`` se inyecta en las pruebas."""

    def __init__(self, client: Any, deployment: str, send_temperature: bool = True) -> None:
        self._client = client
        self.deployment = deployment
        self.send_temperature = send_temperature

    def generate(
        self, system: str, user: str, max_tokens: int = 900, temperature: float = 0.0
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.deployment,  # en Azure, "model" es el nombre del despliegue
            "messages": [
                {"role": "system", "content": system or SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "max_completion_tokens": max_tokens,
        }
        if self.send_temperature:
            kwargs["temperature"] = temperature
        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        if getattr(choice, "finish_reason", None) == "content_filter":
            # El filtro de contenido de Azure cortó la respuesta: se trata como sin sustento
            return NOT_FOUND_TOKEN
        return (choice.message.content or "").strip()


def build_llm(settings: Settings, client: Any = None) -> LLM:
    if settings.llm_backend == "azure_openai":
        return AzureOpenAILLM(
            client or build_azure_openai_client(settings),
            settings.azure_openai_chat_deployment,
            settings.azure_openai_send_temperature,
        )
    return ExtractiveLLM()
