"""Guardrails de entrada y salida.

- ``LocalGuardrail``: reglas propias (inyección, PII). Funciona sin Azure.
- ``AzureContentSafetyGuardrail``: Azure AI Content Safety. Prompt Shields
  detecta ataques directos en la pregunta y ataques indirectos escondidos en
  los documentos recuperados; la moderación de texto bloquea contenido dañino
  por severidad. Se combina con las reglas locales: basta que una capa bloquee.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import httpx
from pydantic import SecretStr

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

    def check_documents(self, query: str, documents: list[str]) -> list[int]:
        """Índices de los documentos recuperados con instrucciones ocultas."""
        ...


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

    def check_documents(self, query: str, documents: list[str]) -> list[int]:
        # En local la cuarentena de la ingesta ya revisó cada fragmento con las mismas reglas
        return []


class AzureContentSafetyGuardrail:
    """Prompt Shields y moderación de texto de Azure AI Content Safety.

    ``http`` y ``token_provider`` se inyectan en las pruebas. Sin API key se
    autentica con la identidad administrada (token de Microsoft Entra ID).
    """

    MAX_DOCS = 5
    MAX_DOC_CHARS = 2000  # Prompt Shields limita el tamaño total de la solicitud

    def __init__(
        self,
        endpoint: str,
        api_version: str = "2024-09-01",
        api_key: SecretStr | None = None,
        max_severity: int = 2,
        http: httpx.Client | None = None,
        token_provider: Callable[[], str] | None = None,
    ) -> None:
        self.base = endpoint.rstrip("/") + "/contentsafety/text"
        self.api_version = api_version
        self.api_key = api_key
        self.max_severity = max_severity
        self._http = http or httpx.Client(timeout=10.0)
        self._token_provider = token_provider
        self._local = LocalGuardrail()

    def _post(self, operation: str, body: dict[str, Any]) -> dict[str, Any]:
        from riskrag.azure_auth import auth_headers

        resp = self._http.post(
            f"{self.base}:{operation}",
            params={"api-version": self.api_version},
            headers=auth_headers(self.api_key, "Ocp-Apim-Subscription-Key", self._token_provider),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    def _harmful(self, text: str) -> list[str]:
        out = self._post("analyze", {"text": text[:10000], "outputType": "FourSeverityLevels"})
        return [
            f"azure:harm:{c['category'].lower()}"
            for c in out.get("categoriesAnalysis", [])
            if int(c.get("severity", 0)) > self.max_severity
        ]

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
        if source == "INPUT":
            shield = self._post("shieldPrompt", {"userPrompt": local.text[:10000], "documents": []})
            if shield.get("userPromptAnalysis", {}).get("attackDetected"):
                return GuardrailDecision(False, text, [*local.flags, "azure:prompt_attack"])
        harm = self._harmful(local.text)
        if harm:
            return GuardrailDecision(
                False, "Contenido bloqueado por política.", [*local.flags, *harm]
            )
        return local

    def check_documents(self, query: str, documents: list[str]) -> list[int]:
        flagged: list[int] = []
        for start in range(0, len(documents), self.MAX_DOCS):
            batch = [d[: self.MAX_DOC_CHARS] for d in documents[start : start + self.MAX_DOCS]]
            out = self._post("shieldPrompt", {"userPrompt": query[:2000], "documents": batch})
            for i, analysis in enumerate(out.get("documentsAnalysis", [])):
                if analysis.get("attackDetected"):
                    flagged.append(start + i)
        return flagged


def build_guardrail(settings: Any) -> Guardrail:
    if settings.guardrail_backend == "azure_content_safety":
        if not settings.azure_content_safety_endpoint:
            raise ValueError("RISKRAG_AZURE_CONTENT_SAFETY_ENDPOINT es obligatorio")
        return AzureContentSafetyGuardrail(
            settings.azure_content_safety_endpoint,
            settings.azure_content_safety_api_version,
            settings.azure_content_safety_api_key,
            settings.azure_content_safety_max_severity,
        )
    return LocalGuardrail()
