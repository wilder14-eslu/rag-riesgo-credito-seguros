import httpx
import pytest

from riskrag.agent.orchestrator import LocalAgent
from riskrag.tools.credit_model import ApplicantFeatures, CreditModelClient, CreditModelUnavailable
from riskrag.tools.regulatory import classify_by_arrears, compute_provision


@pytest.mark.parametrize(
    "ctype,days,expected",
    [
        ("consumo_no_revolvente", 8, "Normal"),
        ("consumo_no_revolvente", 9, "CPP"),
        ("microempresas", 30, "CPP"),
        ("microempresas", 31, "Deficiente"),
        ("pequenas_empresas", 120, "Dudoso"),
        ("pequenas_empresas", 121, "Pérdida"),
        ("hipotecarios_vivienda", 30, "Normal"),
        ("hipotecarios_vivienda", 365, "Dudoso"),
        ("hipotecarios_vivienda", 366, "Pérdida"),
    ],
)
def test_classification_boundaries(services, ctype, days, expected):
    assert classify_by_arrears(services.tables, ctype, days).categoria == expected


def test_non_retail_requires_payment_capacity(services):
    res = classify_by_arrears(services.tables, "corporativos", 40)
    assert res.categoria is None and "capacidad de pago" in res.nota


def test_provision_generic_and_specific(services):
    assert (
        str(compute_provision(services.tables, "hipotecarios_vivienda", "Normal", 100000).provision)
        == "700.00"
    )
    mixed = compute_provision(
        services.tables,
        "microempresas",
        "Deficiente",
        10000,
        covered_amount=4000,
        guarantee="garantia_preferida",
    )
    # 6000 x 25% + 4000 x 12.5% = 1500 + 500
    assert str(mixed.provision) == "2000.00"


def test_provision_validates_inputs(services):
    with pytest.raises(ValueError):
        compute_provision(services.tables, "microempresas", "CPP", 100, covered_amount=200)
    with pytest.raises(ValueError):
        compute_provision(services.tables, "microempresas", "CPP", 0)


def _features():
    return ApplicantFeatures(
        revolving_utilization_unsecured=0.3,
        age=40,
        debt_ratio=0.4,
        monthly_income=5000,
        number_open_credit_lines=5,
    )


def test_credit_model_client_filters_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/predict"
        return httpx.Response(
            200,
            json={
                "probability": 0.12,
                "decision": "aprobar",
                "risk_band": "B",
                "top_factors": [],
                "secreto": "x",
            },
        )

    client = CreditModelClient("http://modelo.local", transport=httpx.MockTransport(handler))
    out = client.predict(_features())
    assert out["probability"] == 0.12 and "secreto" not in out


def test_credit_model_without_url_fails_explicitly():
    with pytest.raises(CreditModelUnavailable):
        CreditModelClient(None).predict(_features())


def test_agent_routes(services):
    agent = LocalAgent(services)
    assert agent.run("¿Qué es la LGD?").tool == "glosario"
    calc = agent.run(
        "Calcula la provisión de un crédito a microempresas con 70 días de atraso por S/ 10,000"
    )
    assert calc.tool == "clasificar_deudor+calcular_provision" and "6000.00" in calc.answer.answer
    assert agent.run("¿Quién ganó el mundial de fútbol?").intent == "fuera_de_dominio"
    pii = agent.run("Mi DNI es 45678912, ¿qué categoría tengo con 20 días de atraso en consumo?")
    assert "pii:DNI" in pii.answer.security_flags and "45678912" not in pii.answer.answer
