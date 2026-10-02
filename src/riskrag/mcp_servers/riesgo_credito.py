"""Servidor MCP ``riesgo-credito``: clasificación, provisiones y probabilidad de default.

Separado de ``rag-normativa`` para aislar permisos: este servidor puede
llamar a la API del modelo de default; el otro solo lee el índice.

Uso local:
    python -m riskrag.mcp_servers.riesgo_credito
"""

from __future__ import annotations

from typing import Any

from riskrag.factory import get_services
from riskrag.mcp_servers._compat import create_server, run_server
from riskrag.tools.credit_model import ApplicantFeatures, CreditModelUnavailable
from riskrag.tools.regulatory import (
    Category,
    CreditType,
    Guarantee,
    classify_by_arrears,
    compute_provision,
)

mcp = create_server(
    "riesgo-credito",
    instructions=(
        "Cálculos deterministas de riesgo crediticio según tablas normativas versionadas y "
        "predicción de probabilidad de default. No hagas cálculos por tu cuenta: usa estas herramientas."
    ),
)


@mcp.tool()
def clasificar_deudor(tipo_credito: CreditType, dias_atraso: int) -> dict[str, Any]:
    """Clasifica al deudor minorista o hipotecario según días de atraso (Res. SBS 11356-2008)."""
    services = get_services()
    services.audit.log("mcp_tool", tool="clasificar_deudor", server="riesgo-credito")
    if not 0 <= dias_atraso <= 10_000:
        return {"error": "dias_atraso fuera de rango"}
    return classify_by_arrears(services.tables, tipo_credito, dias_atraso).model_dump()


@mcp.tool()
def calcular_provision(
    tipo_credito: CreditType,
    categoria: Category,
    monto: float,
    monto_cubierto: float = 0.0,
    garantia: Guarantee = "sin_garantia_preferida",
) -> dict[str, Any]:
    """Calcula la provisión simplificada (sin componente procíclico) y explica el detalle."""
    services = get_services()
    services.audit.log("mcp_tool", tool="calcular_provision", server="riesgo-credito")
    try:
        return compute_provision(
            services.tables, tipo_credito, categoria, monto, monto_cubierto, garantia
        ).model_dump(mode="json")
    except ValueError as exc:
        return {"error": str(exc)}


@mcp.tool()
def predecir_default(solicitante: ApplicantFeatures) -> dict[str, Any]:
    """Probabilidad de default, decisión y factores principales del modelo conectado."""
    services = get_services()
    services.audit.log("mcp_tool", tool="predecir_default", server="riesgo-credito")
    try:
        return services.credit_model.predict(solicitante)
    except CreditModelUnavailable as exc:
        return {"error": str(exc)}


if __name__ == "__main__":  # pragma: no cover
    run_server(mcp)
