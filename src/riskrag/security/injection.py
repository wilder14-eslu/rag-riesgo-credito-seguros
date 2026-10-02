"""Detección heurística de inyección de prompt (OWASP LLM01 y LLM07).

Se usa en dos lugares:

- Consulta del usuario (inyección directa): se bloquea o se marca.
- Documentos en la ingesta (inyección indirecta): un fragmento con
  instrucciones dirigidas al modelo se pone en cuarentena y no se indexa.

Es una primera barrera barata y explicable, no la única: en AWS se suma el
filtro de ataques de prompt de Bedrock Guardrails y, en el prompt, el texto
recuperado va delimitado y declarado como dato, nunca como instrucción.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from riskrag.nlp.normalize import strip_accents

_RULES: list[tuple[str, str, float]] = [
    # (nombre, patrón sobre texto sin tildes y en minúsculas, peso)
    (
        "override_es",
        r"\b(ignora|olvida|omite|descarta)\w*\b.{0,40}\b(instruccion|regla|indicacion|anterior|previo)",
        0.9,
    ),
    (
        "override_en",
        r"\b(ignore|disregard|forget)\b.{0,40}\b(instruction|rule|previous|above|prior)",
        0.9,
    ),
    (
        "role_hijack",
        r"\b(ahora eres|a partir de ahora (eres|actua)|actua como|you are now|act as|pretend to be)\b",
        0.6,
    ),
    (
        "prompt_leak_es",
        r"\b(muestra|revela|imprime|repite|dime)\w*\b.{0,40}\b(prompt|instrucciones( del sistema)?|system prompt|configuracion)",
        0.8,
    ),
    (
        "prompt_leak_en",
        r"\b(show|reveal|print|repeat)\b.{0,40}\b(system prompt|your instructions|hidden prompt)",
        0.8,
    ),
    (
        "jailbreak",
        r"\b(jailbreak|dan mode|modo desarrollador|developer mode|sin restricciones|no restrictions)\b",
        0.8,
    ),
    (
        "tool_abuse",
        r"\b(ejecuta|llama|invoca|run|execute|call)\b.{0,30}\b(herramienta|tool|funcion|function|comando|command|shell)",
        0.5,
    ),
    (
        "exfiltration",
        r"\b(envia|manda|send|post|exfiltra)\w*\b.{0,60}\b(https?://|url|correo|email|webhook)",
        0.8,
    ),
    (
        "fake_system",
        r"(<\s*/?\s*(system|assistant|instrucciones)\s*>|\[\s*(system|inst)\s*\]|###\s*(system|instruction))",
        0.8,
    ),
    (
        "data_dump",
        r"\b(todos los|all the|lista completa de|lista de|listado de)\b.{0,30}\b(clientes|usuarios|deudores|dni|datos personales|customers|users)",
        0.8,
    ),
    (
        "prompt_leak_rules",
        r"\b(repite|dime|cuales son|lista|copia)\w*\b.{0,40}\b(reglas|instrucciones|indicaciones)\b.{0,30}\b(te dieron|del sistema|internas|ocultas|iniciales|antes de esta)",
        0.8,
    ),
]
_COMPILED = [(name, re.compile(p), w) for name, p, w in _RULES]


@dataclass
class InjectionReport:
    score: float
    matched: list[str] = field(default_factory=list)

    @property
    def is_attack(self) -> bool:
        return self.score >= 0.75

    @property
    def is_suspicious(self) -> bool:
        return self.score >= 0.5


def scan(text: str) -> InjectionReport:
    norm = strip_accents(text.lower())
    matched = [name for name, rx, _ in _COMPILED if rx.search(norm)]
    weights = sorted((w for name, _, w in _RULES if name in matched), reverse=True)
    # Combinación tipo "o probabilístico": varias señales débiles suman
    score = 0.0
    for w in weights:
        score = score + w * (1 - score)
    return InjectionReport(score=round(score, 3), matched=matched)


def neutralize_for_prompt(text: str) -> str:
    """Escapa delimitadores para que un fragmento no pueda cerrar su etiqueta."""
    return text.replace("<", "‹").replace(">", "›")
