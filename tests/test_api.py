import hashlib

import pytest
from fastapi.testclient import TestClient

import riskrag.api.main as api_main
import riskrag.api.security as api_security
from riskrag.config import get_settings


@pytest.fixture()
def client(services, monkeypatch):
    monkeypatch.setattr(api_main, "get_services", lambda: services)
    api_security._limiter = None
    settings = services.settings.model_copy(
        update={
            "api_keys_sha256": [hashlib.sha256(b"clave-test").hexdigest()],
            "rate_limit_per_minute": 3,
        }
    )
    api_main.app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(api_main.app)
    api_main.app.dependency_overrides.clear()
    api_security._limiter = None


def test_health_and_security_headers(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]


def test_requires_valid_api_key(client):
    assert client.post("/v1/ask", json={"pregunta": "¿Qué es la PD?"}).status_code == 401
    bad = client.post("/v1/ask", json={"pregunta": "¿Qué es la PD?"}, headers={"x-api-key": "otra"})
    assert bad.status_code == 401


def test_ask_and_rate_limit(client):
    h = {"x-api-key": "clave-test"}
    r = client.post("/v1/ask", json={"pregunta": "¿Qué es la PD?"}, headers=h)
    assert r.status_code == 200 and r.json()["herramienta"] == "glosario"
    client.post("/v1/ask", json={"pregunta": "¿Qué es la LGD?"}, headers=h)
    client.post("/v1/ask", json={"pregunta": "¿Qué es la EAD?"}, headers=h)
    assert (
        client.post("/v1/ask", json={"pregunta": "¿Qué es el CSM?"}, headers=h).status_code == 429
    )


def test_tool_endpoints_validate_input(client):
    h = {"x-api-key": "clave-test"}
    ok = client.post(
        "/v1/tools/clasificar_deudor",
        json={"tipo_credito": "microempresas", "dias_atraso": 45},
        headers=h,
    )
    assert ok.status_code == 200 and ok.json()["categoria"] == "Deficiente"
    bad = client.post(
        "/v1/tools/clasificar_deudor",
        json={"tipo_credito": "inventado", "dias_atraso": -1},
        headers=h,
    )
    assert bad.status_code == 422


def test_oversized_question_rejected(client):
    r = client.post("/v1/ask", json={"pregunta": "x" * 2001}, headers={"x-api-key": "clave-test"})
    assert r.status_code == 422
