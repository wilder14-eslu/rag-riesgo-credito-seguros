"""Guardrails de entrada y salida.

- ``LocalGuardrail``: reglas propias (inyección, PII). Funciona sin AWS.
- ``BedrockGuardrail``: llama a la API ``ApplyGuardrail`` de Bedrock con el
  guardrail configurado en Terraform (filtro de ataques de prompt, PII,
  temas denegados, grounding). Se combina con las reglas locales: basta que
  una de las dos capas bloquee.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from riskrag.security.injection import scan
from riskrag.security.pii import mask_pii


@dataclass
class GuardrailDecision:
    allowed: bool
    text: str
    flags: list[str] = field(default_factory=list)


class Guardrail(Protocol):
    def check(
        self,
        text: str,
        source: Literal["INPUT", "OUTPUT"],
        *,
        query: str | None = None,
        evidence: list[str] | None = None,
    ) -> GuardrailDecision: ...


class LocalGuardrail:
    def check(
        self,
        text: str,
        source: Literal["INPUT", "OUTPUT"],
        *,
        query: str | None = None,
        evidence: list[str] | None = None,
    ) -> GuardrailDecision:
        flags: list[str] = []
        if source == "INPUT":
            report = scan(text)
            if report.is_attack:
                return GuardrailDecision(False, text, [f"injection:{m}" for m in report.matched])
            if report.is_suspicious:
                flags += [f"suspicious:{m}" for m in report.matched]
        masked, kinds = mask_pii(text)
        flags += [f"pii:{k}" for k in kinds]
        return GuardrailDecision(True, masked, flags)


def _has_blocking_action(node: Any) -> bool:
    """True si alguna evaluación del guardrail tiene ``action == "BLOCKED"``.

    ``GUARDRAIL_INTERVENED`` también aparece cuando el guardrail solo enmascaró
    datos (ANONYMIZED); en ese caso la respuesta sigue siendo válida.
    """
    if isinstance(node, dict):
        if node.get("action") == "BLOCKED":
            return True
        return any(_has_blocking_action(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_blocking_action(v) for v in node)
    return False


class BedrockGuardrail:
    def __init__(self, guardrail_id: str, version: str, region: str, client: Any = None) -> None:
        if client is None:
            import boto3

            client = boto3.client("bedrock-runtime", region_name=region)
        self._client = client
        self.guardrail_id = guardrail_id
        self.version = version
        self._local = LocalGuardrail()

    def check(
        self,
        text: str,
        source: Literal["INPUT", "OUTPUT"],
        *,
        query: str | None = None,
        evidence: list[str] | None = None,
    ) -> GuardrailDecision:
        local = self._local.check(text, source)
        if not local.allowed:
            return local
        if source == "OUTPUT" and evidence and query:
            # Con calificadores, el filtro de grounding compara la respuesta con la evidencia
            content = [
                {
                    "text": {
                        "text": "\n\n".join(evidence)[:20000],
                        "qualifiers": ["grounding_source"],
                    }
                },
                {"text": {"text": query, "qualifiers": ["query"]}},
                {"text": {"text": local.text, "qualifiers": ["guard_content"]}},
            ]
        else:
            content = [{"text": {"text": local.text}}]
        resp = self._client.apply_guardrail(
            guardrailIdentifier=self.guardrail_id,
            guardrailVersion=self.version,
            source=source,
            content=content,
        )
        if resp.get("action") != "GUARDRAIL_INTERVENED":
            return local
        outputs = resp.get("outputs") or [{"text": "Contenido bloqueado por política."}]
        if _has_blocking_action(resp.get("assessments", [])):
            return GuardrailDecision(False, outputs[0]["text"], [*local.flags, "bedrock:blocked"])
        # Solo enmascaró: se usa el texto anonimizado
        return GuardrailDecision(True, outputs[0]["text"], [*local.flags, "bedrock:anonymized"])


def build_guardrail(backend: str, guardrail_id: str | None, version: str, region: str) -> Guardrail:
    if backend == "bedrock" and guardrail_id:
        return BedrockGuardrail(guardrail_id, version, region)
    return LocalGuardrail()
