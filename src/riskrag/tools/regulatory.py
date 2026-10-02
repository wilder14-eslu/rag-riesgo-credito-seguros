"""Herramientas deterministas: clasificación por atraso y cálculo de provisiones.

El LLM nunca hace aritmética regulatoria. Estas funciones leen tablas
versionadas en YAML (con fuente y fecha de verificación), validan entradas y
devuelven el resultado junto con la referencia normativa, para que la
respuesta sea reproducible y auditable.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

CreditType = Literal[
    "corporativos",
    "grandes_empresas",
    "medianas_empresas",
    "pequenas_empresas",
    "microempresas",
    "consumo_revolvente",
    "consumo_no_revolvente",
    "hipotecarios_vivienda",
]
Category = Literal["Normal", "CPP", "Deficiente", "Dudoso", "Pérdida"]
Guarantee = Literal[
    "sin_garantia_preferida", "garantia_preferida", "garantia_preferida_muy_rapida_realizacion"
]


@lru_cache(maxsize=4)
def load_tables(path: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


class ClassificationResult(BaseModel):
    tipo_credito: str
    dias_atraso: int
    categoria: Category | None
    referencia: str
    nota: str | None = None
    fuente: str


def classify_by_arrears(
    tables: dict[str, Any], credit_type: CreditType, days: int
) -> ClassificationResult:
    if days < 0:
        raise ValueError("Los días de atraso no pueden ser negativos.")
    info = tables["tipos_credito"][credit_type]
    group = tables["clasificacion_por_atraso"][info["grupo"]]
    source = f"{tables['norma']} ({tables['url']})"
    if info["grupo"] == "no_minorista":
        return ClassificationResult(
            tipo_credito=credit_type,
            dias_atraso=days,
            categoria=None,
            referencia=group["referencia"],
            nota=group["nota"].strip(),
            fuente=source,
        )
    for category in ("Normal", "CPP", "Deficiente", "Dudoso", "Pérdida"):
        lo, hi = group[category]
        if days >= lo and (hi is None or days <= hi):
            return ClassificationResult(
                tipo_credito=credit_type,
                dias_atraso=days,
                categoria=category,
                referencia=group["referencia"],
                fuente=source,
            )
    raise ValueError("No se encontró categoría para los días indicados.")  # pragma: no cover


class ProvisionResult(BaseModel):
    tipo_credito: str
    categoria: Category
    monto_total: Decimal
    monto_cubierto: Decimal
    tasa_no_cubierta_pct: Decimal
    tasa_cubierta_pct: Decimal
    provision: Decimal
    detalle: list[str] = Field(default_factory=list)
    referencia: str
    alcance: str
    fuente: str


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_provision(
    tables: dict[str, Any],
    credit_type: CreditType,
    category: Category,
    amount: float,
    covered_amount: float = 0.0,
    guarantee: Guarantee = "sin_garantia_preferida",
) -> ProvisionResult:
    """Provisión simplificada: genérica para Normal, específica para el resto.

    Para categorías distintas de Normal, la parte cubierta por la garantía usa
    la tabla de esa garantía y la parte no cubierta usa la tabla 1.
    """
    total, covered = Decimal(str(amount)), Decimal(str(covered_amount))
    if total <= 0:
        raise ValueError("El monto debe ser mayor que cero.")
    if covered < 0 or covered > total:
        raise ValueError("El monto cubierto debe estar entre 0 y el monto total.")
    source = f"{tables['norma']} ({tables['url']})"
    spec = tables["provision_especifica"]
    detail: list[str] = []

    if category == "Normal":
        rate = Decimal(str(tables["tipos_credito"][credit_type]["generica"]))
        provision = total * rate / 100
        detail.append(f"Provisión genérica {rate}% sobre {total}")
        rate_cov = rate
    else:
        rate = Decimal(str(spec["tabla_1"][category]))
        table_cov = tables["uso_tablas"][guarantee]
        rate_cov = Decimal(str(spec[table_cov][category]))
        uncovered = total - covered
        provision = uncovered * rate / 100 + covered * rate_cov / 100
        detail.append(f"Parte no cubierta {uncovered} x {rate}% (tabla_1)")
        if covered:
            detail.append(f"Parte cubierta {covered} x {rate_cov}% ({table_cov})")

    return ProvisionResult(
        tipo_credito=credit_type,
        categoria=category,
        monto_total=_q(total),
        monto_cubierto=_q(covered),
        tasa_no_cubierta_pct=rate,
        tasa_cubierta_pct=rate_cov,
        provision=_q(provision),
        detalle=detail,
        referencia=spec["referencia"],
        alcance=" ".join(tables["alcance"].split()),
        fuente=source,
    )
