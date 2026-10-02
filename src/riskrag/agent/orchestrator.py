"""Agente orquestador: decide qué herramienta usar para cada pregunta.

Modo local (por defecto): enrutamiento por intención con extracción de
parámetros por reglas. Es transparente, rápido y fácil de evaluar.

Modo Bedrock (``BedrockToolAgent``): Claude elige herramientas con la API
Converse y ``toolConfig``. Usa las mismas funciones que los servidores MCP,
con un máximo de pasos y lista explícita de herramientas permitidas
(OWASP LLM06: agencia excesiva).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from riskrag.factory import Services
from riskrag.models import Answer
from riskrag.nlp.intent import classify_intent
from riskrag.nlp.normalize import strip_accents
from riskrag.nlp.query_expansion import load_glossary, lookup
from riskrag.security.guardrails import LocalGuardrail
from riskrag.security.validation import sanitize_query
from riskrag.tools.regulatory import classify_by_arrears, compute_provision

_CREDIT_TYPES = {
    "microempresa": "microempresas",
    "pequena empresa": "pequenas_empresas",
    "pequenas empresas": "pequenas_empresas",
    "mediana empresa": "medianas_empresas",
    "medianas empresas": "medianas_empresas",
    "gran empresa": "grandes_empresas",
    "grandes empresas": "grandes_empresas",
    "corporativo": "corporativos",
    "consumo revolvente": "consumo_revolvente",
    "tarjeta de credito": "consumo_revolvente",
    "consumo no revolvente": "consumo_no_revolvente",
    "consumo": "consumo_no_revolvente",
    "hipotecario": "hipotecarios_vivienda",
    "vivienda": "hipotecarios_vivienda",
}
_CATEGORIES = {
    "normal": "Normal",
    "cpp": "CPP",
    "deficiente": "Deficiente",
    "dudoso": "Dudoso",
    "perdida": "Pérdida",
}
_DAYS_RE = re.compile(r"(\d{1,4})\s*dias")
_AMOUNT_RE = re.compile(r"(?:s/\.?|soles|monto(?: de)?)\s*([\d.,]+)|([\d.,]+)\s*soles")
_TERM_RE = re.compile(
    r"^\s*¿?\s*(?:que es|que significa|define|definicion de|significado de)\s+(?:el |la |los |las |un |una )?(.+?)\s*\??\s*$"
)

OUT_OF_DOMAIN = (
    "Estoy especializado en riesgo crediticio y seguros. Puedo responder sobre normativa, "
    "clasificación del deudor, provisiones, conceptos como PD o IFRS 9, y estimar la "
    "probabilidad de default con el modelo conectado."
)


@dataclass
class AgentResult:
    intent: str
    tool: str | None
    answer: Answer
    tool_output: dict[str, Any] = field(default_factory=dict)


def _parse_amount(text: str) -> float | None:
    m = _AMOUNT_RE.search(text)
    if not m:
        return None
    raw = (m.group(1) or m.group(2)).rstrip(".,")
    raw = (
        raw.replace(",", "")
        if raw.count(",") and raw.count(".") <= 1
        else raw.replace(".", "").replace(",", ".")
    )
    try:
        return float(raw)
    except ValueError:
        return None


def _find_credit_type(q: str) -> str | None:
    for key in sorted(_CREDIT_TYPES, key=len, reverse=True):
        if key in q:
            return _CREDIT_TYPES[key]
    return None


class LocalAgent:
    def __init__(self, services: Services) -> None:
        self.s = services
        self.glossary = load_glossary(str(services.settings.glossary_path))
        self._guard = LocalGuardrail()

    def run(self, question: str, actor: str | None = None) -> AgentResult:
        question = sanitize_query(question, self.s.settings.max_query_chars)
        guard = self._guard.check(question, "INPUT")
        if not guard.allowed:  # mismo bloqueo que el pipeline, antes de cualquier herramienta
            ans = self.s.pipeline.ask(question, actor=actor)
            return AgentResult("bloqueado", None, ans)
        # Las herramientas trabajan sobre la consulta con PII enmascarada
        result = self._route(guard.text, actor)
        for flag in guard.flags:
            if flag not in result.answer.security_flags:
                result.answer.security_flags.append(flag)
        return result

    def _route(self, question: str, actor: str | None) -> AgentResult:
        intent = classify_intent(question).intent
        q = strip_accents(question.lower())
        self.s.audit.log("agent_route", actor=actor, intent=intent)

        # Un término del glosario se reconoce aunque la pregunta no tenga otras pistas del dominio
        m = _TERM_RE.match(q)
        entry = lookup(m.group(1), self.glossary) if m else None
        if entry:
            text = f"{entry.term}: {entry.definition}"
            if entry.source:
                text += f" (Fuente: {entry.source})"
            return AgentResult(
                "glosario", "glosario", Answer(question=question, answer=text, intent="glosario")
            )
        if intent == "fuera_de_dominio":
            return AgentResult(
                intent,
                None,
                Answer(question=question, answer=OUT_OF_DOMAIN, abstained=True, intent=intent),
            )
        if intent == "glosario":
            intent = "normativa"  # si no está en el glosario, se busca en el corpus
        if intent == "calculo":
            result = self._calculation(question, q, actor)
            if result is not None:
                return result
            intent = "normativa"
        if intent == "prediccion":
            text = (
                "Para estimar la probabilidad de default necesito los datos del solicitante "
                "en formato estructurado. Usa el endpoint POST /tools/predecir_default o la "
                "herramienta MCP 'predecir_default' con los campos del modelo."
            )
            return AgentResult(
                intent, None, Answer(question=question, answer=text, intent=intent, abstained=True)
            )
        ans = self.s.pipeline.ask(question, actor=actor, intent="normativa")
        return AgentResult("normativa", "buscar_normativa", ans)

    def _calculation(self, question: str, q: str, actor: str | None) -> AgentResult | None:
        credit_type = _find_credit_type(q)
        days_m = _DAYS_RE.search(q)
        amount = _parse_amount(q)
        category = next((v for k, v in _CATEGORIES.items() if re.search(rf"\b{k}\b", q)), None)

        if credit_type and days_m:
            res = classify_by_arrears(self.s.tables, credit_type, int(days_m.group(1)))  # type: ignore[arg-type]
            out = res.model_dump()
            if res.categoria is None:
                text = f"{res.nota} Referencia: {res.referencia}."
            else:
                text = (
                    f"Con {res.dias_atraso} días de atraso, un crédito de tipo "
                    f"{credit_type.replace('_', ' ')} se clasifica como {res.categoria} "
                    f"({res.referencia}, {res.fuente})."
                )
                category = category or res.categoria
            tool = "clasificar_deudor"
            if amount and res.categoria:
                prov = compute_provision(self.s.tables, credit_type, res.categoria, amount)  # type: ignore[arg-type]
                out["provision"] = prov.model_dump(mode="json")
                text += (
                    f" La provisión simplificada sobre S/ {prov.monto_total} es S/ {prov.provision} "
                    f"({'; '.join(prov.detalle)}). {prov.alcance}"
                )
                tool = "clasificar_deudor+calcular_provision"
            self.s.audit.log("tool_call", actor=actor, tool=tool, ok=True)
            return AgentResult(
                "calculo", tool, Answer(question=question, answer=text, intent="calculo"), out
            )
        if credit_type and category and amount:
            prov = compute_provision(self.s.tables, credit_type, category, amount)  # type: ignore[arg-type]
            text = (
                f"Provisión simplificada para S/ {prov.monto_total} en categoría {category}: "
                f"S/ {prov.provision} ({'; '.join(prov.detalle)}). Referencia: {prov.referencia}. "
                f"{prov.alcance}"
            )
            self.s.audit.log("tool_call", actor=actor, tool="calcular_provision", ok=True)
            return AgentResult(
                "calculo",
                "calcular_provision",
                Answer(question=question, answer=text, intent="calculo"),
                prov.model_dump(mode="json"),
            )
        return None


TOOL_SPECS = [
    {
        "toolSpec": {
            "name": "buscar_normativa",
            "description": "Busca en normativa y documentos técnicos de riesgo crediticio y seguros y devuelve una respuesta con citas.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {"pregunta": {"type": "string"}},
                    "required": ["pregunta"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "clasificar_deudor",
            "description": "Clasifica al deudor según días de atraso y tipo de crédito (Res. SBS 11356-2008).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "tipo_credito": {
                            "type": "string",
                            "enum": sorted(set(_CREDIT_TYPES.values())),
                        },
                        "dias_atraso": {"type": "integer", "minimum": 0, "maximum": 10000},
                    },
                    "required": ["tipo_credito", "dias_atraso"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "calcular_provision",
            "description": "Calcula la provisión simplificada por categoría, monto y garantía.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "tipo_credito": {
                            "type": "string",
                            "enum": sorted(set(_CREDIT_TYPES.values())),
                        },
                        "categoria": {"type": "string", "enum": list(_CATEGORIES.values())},
                        "monto": {"type": "number", "exclusiveMinimum": 0},
                        "monto_cubierto": {"type": "number", "minimum": 0},
                    },
                    "required": ["tipo_credito", "categoria", "monto"],
                }
            },
        }
    },
]


class BedrockToolAgent:  # pragma: no cover - requiere AWS
    """Agente con uso de herramientas en Bedrock. Máximo ``max_steps`` llamadas."""

    ALLOWED = {"buscar_normativa", "clasificar_deudor", "calcular_provision"}

    def __init__(self, services: Services, max_steps: int = 4) -> None:
        import boto3

        self.s = services
        self.max_steps = max_steps
        self._client = boto3.client("bedrock-runtime", region_name=services.settings.aws_region)

    def _call_tool(self, name: str, args: dict[str, Any], actor: str | None) -> dict[str, Any]:
        if name not in self.ALLOWED:
            return {"error": "herramienta no permitida"}
        self.s.audit.log(
            "tool_call", actor=actor, tool=name, args=json.dumps(args, ensure_ascii=False)
        )
        if name == "buscar_normativa":
            return self.s.pipeline.ask(str(args["pregunta"]), actor=actor).model_dump(mode="json")
        if name == "clasificar_deudor":
            return classify_by_arrears(
                self.s.tables, args["tipo_credito"], int(args["dias_atraso"])
            ).model_dump()
        return compute_provision(
            self.s.tables,
            args["tipo_credito"],
            args["categoria"],
            float(args["monto"]),
            float(args.get("monto_cubierto", 0)),
        ).model_dump(mode="json")

    def run(self, question: str, actor: str | None = None) -> str:
        question = sanitize_query(question, self.s.settings.max_query_chars)
        messages: list[dict[str, Any]] = [{"role": "user", "content": [{"text": question}]}]
        system = [
            {
                "text": "Eres un analista de riesgo crediticio. Usa herramientas para normativa y "
                "cálculos; nunca calcules tú. Cita las fuentes que devuelvan las herramientas."
            }
        ]
        for _ in range(self.max_steps):
            resp = self._client.converse(
                modelId=self.s.settings.bedrock_llm_model_id,
                system=system,
                messages=messages,
                toolConfig={"tools": TOOL_SPECS},
                inferenceConfig={"maxTokens": 900, "temperature": 0.0},
            )
            msg = resp["output"]["message"]
            messages.append(msg)
            if resp.get("stopReason") != "tool_use":
                return "".join(p.get("text", "") for p in msg["content"])
            results = []
            for part in msg["content"]:
                if "toolUse" in part:
                    tu = part["toolUse"]
                    try:
                        out = self._call_tool(tu["name"], tu.get("input", {}), actor)
                        results.append(
                            {
                                "toolResult": {
                                    "toolUseId": tu["toolUseId"],
                                    "content": [{"json": out}],
                                }
                            }
                        )
                    except Exception as exc:  # noqa: BLE001
                        results.append(
                            {
                                "toolResult": {
                                    "toolUseId": tu["toolUseId"],
                                    "status": "error",
                                    "content": [{"text": str(exc)}],
                                }
                            }
                        )
            messages.append({"role": "user", "content": results})
        return "Se alcanzó el máximo de pasos permitidos sin una respuesta final."
