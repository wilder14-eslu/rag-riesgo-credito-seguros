"""Clasificación de intención de la consulta.

La intención decide qué herramienta usa el agente:

- ``normativa``: buscar y citar normas (herramienta ``buscar_normativa``)
- ``calculo``: provisión o clasificación determinista (``calcular_provision``,
  ``clasificar_deudor``)
- ``prediccion``: probabilidad de default de un solicitante (``predecir_default``)
- ``glosario``: definición de un término (``glosario``)
- ``fuera_de_dominio``: el asistente declina con amabilidad

La v1 usa reglas ponderadas y explicables; el conjunto de evaluación incluye
la intención esperada de cada pregunta para medir exactitud. Si las reglas no
alcanzan la meta, se entrena un clasificador TF-IDF + regresión logística o se
delega la decisión al LLM con uso de herramientas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from riskrag.nlp.normalize import strip_accents

INTENTS = ("normativa", "calculo", "prediccion", "glosario", "fuera_de_dominio")

_RULES: dict[str, list[tuple[str, float]]] = {
    "calculo": [
        (r"\bcalcul\w*", 2.0),
        (r"\bcuanto\b.*\bprovision", 2.5),
        (r"\bprovision\w*\b.*\b(s/|soles|monto|\d)", 2.0),
        (r"\b\d+\s*dias\b.*\b(categoria|clasific)", 2.5),
        (r"\b(categoria|clasific\w*)\b.*\b\d+\s*dias\b", 2.5),
        (r"\bque categoria\b", 1.5),
        (r"\bmonto\b", 0.8),
    ],
    "prediccion": [
        (r"\bprobabilidad de (default|incumplimiento)\b", 3.0),
        (r"\b(predic|score|scoring|puntaje)\w*", 2.0),
        (r"\beste (cliente|solicitante)\b", 1.5),
        (r"\bingreso mensual\b|\bdebt ratio\b|\butilizacion\b", 1.5),
    ],
    "glosario": [
        (r"^\s*(que es|que significa|define|definicion de|significado de)\b", 2.5),
        (r"\bque quiere decir\b", 2.0),
    ],
    "normativa": [
        (r"\b(resolucion|reglamento|norma\w*|articulo|numeral|capitulo|anexo|sbs|ley)\b", 1.5),
        (r"\b(exige|establece|dispone|segun|requisito\w*|obligatori\w*)\b", 1.2),
        (r"\b(provision\w*|clasificacion|categoria|deudor|garantia\w*)\b", 1.0),
        (r"\b(ifrs|niif|basilea|solvencia|capital|reaseguro|siniestro\w*|prima\w*)\b", 1.2),
    ],
}

_DOMAIN_HINTS = re.compile(
    r"\b(credit\w*|riesgo\w*|deud\w*|provision\w*|seguro\w*|banc\w*|sbs|default|mora|"
    r"atraso\w*|cartera|prestamo\w*|garantia\w*|ifrs|niif|basilea|pd|lgd|ead|ecl|"
    r"prima\w*|siniestr\w*|reaseguro\w*|capital|solvencia|clasific\w*|categoria\w*|"
    r"castig\w*|refinanci\w*|reestructur\w*|cpp|dudoso|deficiente|perdida|encaje\w*|liquidez|bcrp|tasa\w*|interes\w*|financier\w*|aseguradora\w*|poliza\w*)\b"
)


@dataclass(frozen=True)
class IntentResult:
    intent: str
    scores: dict[str, float]
    confidence: float


def classify_intent(query: str) -> IntentResult:
    q = strip_accents(query.lower())
    scores = {intent: 0.0 for intent in INTENTS}
    for intent, rules in _RULES.items():
        for pattern, weight in rules:
            if re.search(pattern, q):
                scores[intent] += weight

    if not _DOMAIN_HINTS.search(q) and max(scores.values()) < 2.0:
        scores["fuera_de_dominio"] = 3.0

    best = max(scores, key=lambda k: scores[k])
    total = sum(scores.values()) or 1.0
    if scores[best] == 0.0:
        best = "normativa"  # por defecto se busca en el corpus
    return IntentResult(intent=best, scores=scores, confidence=round(scores[best] / total, 3))
