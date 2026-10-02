"""API REST del asistente (FastAPI)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from riskrag import __version__
from riskrag.agent.orchestrator import LocalAgent
from riskrag.api.security import SecurityHeadersMiddleware, require_api_key
from riskrag.config import get_settings
from riskrag.factory import get_services
from riskrag.models import Answer
from riskrag.security.validation import InputRejected
from riskrag.tools.credit_model import ApplicantFeatures, CreditModelUnavailable
from riskrag.tools.regulatory import (
    Category,
    ClassificationResult,
    CreditType,
    Guarantee,
    ProvisionResult,
    classify_by_arrears,
    compute_provision,
)

logger = logging.getLogger(__name__)
_settings = get_settings()

app = FastAPI(
    title="RiskRAG: asistente de riesgo crediticio y seguros",
    version=__version__,
    docs_url="/docs" if _settings.env != "prod" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _settings.env != "prod" else None,
)
app.add_middleware(SecurityHeadersMiddleware)


class AskRequest(BaseModel):
    pregunta: str = Field(..., min_length=3, max_length=2000)


class AskResponse(BaseModel):
    intent: str
    herramienta: str | None
    respuesta: Answer
    resultado_herramienta: dict[str, Any] = {}


class ClassifyRequest(BaseModel):
    tipo_credito: CreditType
    dias_atraso: int = Field(..., ge=0, le=10_000)


class ProvisionRequest(BaseModel):
    tipo_credito: CreditType
    categoria: Category
    monto: float = Field(..., gt=0, le=1e12)
    monto_cubierto: float = Field(0.0, ge=0, le=1e12)
    garantia: Guarantee = "sin_garantia_preferida"


@app.exception_handler(InputRejected)
async def _input_rejected(_: Request, exc: InputRejected) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def _unhandled(_: Request, exc: Exception) -> JSONResponse:  # no filtrar detalles internos
    logger.exception("Error no controlado: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Error interno."})


@app.get("/health")
def health() -> JSONResponse:
    """Listo solo si la configuración y el índice cargan (evita tareas "sanas" que fallan)."""
    try:
        get_services()
    except Exception:  # noqa: BLE001
        logger.exception("El servicio no pudo inicializarse")
        return JSONResponse(status_code=503, content={"status": "error", "version": __version__})
    return JSONResponse(content={"status": "ok", "version": __version__})


@app.post("/v1/ask", response_model=AskResponse)
def ask(body: AskRequest, identity: str = Depends(require_api_key)) -> AskResponse:
    result = LocalAgent(get_services()).run(body.pregunta, actor=identity)
    return AskResponse(
        intent=result.intent,
        herramienta=result.tool,
        respuesta=result.answer,
        resultado_herramienta=result.tool_output,
    )


@app.post("/v1/tools/clasificar_deudor", response_model=ClassificationResult)
def classify(
    body: ClassifyRequest, identity: str = Depends(require_api_key)
) -> ClassificationResult:
    services = get_services()
    services.audit.log("api_tool", actor=identity, tool="clasificar_deudor")
    return classify_by_arrears(services.tables, body.tipo_credito, body.dias_atraso)


@app.post("/v1/tools/calcular_provision", response_model=ProvisionResult)
def provision(body: ProvisionRequest, identity: str = Depends(require_api_key)) -> ProvisionResult:
    services = get_services()
    services.audit.log("api_tool", actor=identity, tool="calcular_provision")
    try:
        return compute_provision(
            services.tables,
            body.tipo_credito,
            body.categoria,
            body.monto,
            body.monto_cubierto,
            body.garantia,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/v1/tools/predecir_default")
def predict(body: ApplicantFeatures, identity: str = Depends(require_api_key)) -> dict[str, Any]:
    services = get_services()
    services.audit.log("api_tool", actor=identity, tool="predecir_default")
    try:
        return services.credit_model.predict(body)
    except CreditModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
