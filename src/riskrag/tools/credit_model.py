"""Cliente de la plataforma de riesgo crediticio (credit-risk-ml-platform).

Llama a ``POST /api/v1/predict`` con el contrato de esa API (dataset Give Me
Some Credit). Si no hay URL configurada, responde con un error explícito en
lugar de inventar una probabilidad.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, Field


class ApplicantFeatures(BaseModel):
    """Mismo contrato que ``PredictionRequest`` de credit-risk-ml-platform."""

    revolving_utilization_unsecured: float = Field(..., ge=0)
    age: float = Field(..., ge=18, le=120)
    number_of_time_30_59_days_past_due: float = Field(0, ge=0)
    debt_ratio: float = Field(..., ge=0)
    monthly_income: float = Field(..., ge=0)
    number_open_credit_lines: float = Field(..., ge=0)
    number_of_times_90_days_late: float = Field(0, ge=0)
    number_real_estate_loans: float = Field(0, ge=0)
    number_of_time_60_89_days_past_due: float = Field(0, ge=0)
    number_dependents: float = Field(0, ge=0)


class CreditModelUnavailable(RuntimeError):
    pass


class CreditModelClient:
    def __init__(
        self,
        base_url: str | None,
        timeout_s: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout_s = timeout_s
        self._transport = transport

    def predict(self, features: ApplicantFeatures) -> dict[str, Any]:
        if not self.base_url:
            raise CreditModelUnavailable(
                "No hay URL configurada para el modelo de default (RISKRAG_CREDIT_MODEL_URL)."
            )
        with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
            resp = client.post(f"{self.base_url}/api/v1/predict", json=features.model_dump())
        if resp.status_code != 200:
            raise CreditModelUnavailable(f"El modelo respondió {resp.status_code}.")
        data = resp.json()
        allowed = {"probability", "decision", "risk_band", "top_factors", "model_version"}
        return {k: v for k, v in data.items() if k in allowed}
