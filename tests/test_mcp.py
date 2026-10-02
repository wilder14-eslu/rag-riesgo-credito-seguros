import pytest

pytest.importorskip("mcp")

import riskrag.mcp_servers.rag_normativa as rag_srv  # noqa: E402
import riskrag.mcp_servers.riesgo_credito as risk_srv  # noqa: E402


@pytest.fixture(autouse=True)
def _services(services, monkeypatch):
    monkeypatch.setattr(rag_srv, "get_services", lambda: services)
    monkeypatch.setattr(risk_srv, "get_services", lambda: services)


def test_rag_tools(services):
    out = rag_srv.buscar_normativa(
        "¿Qué tasa de provisión genérica aplica a los créditos hipotecarios para vivienda?"
    )
    assert out["citations"] and "retrieved_ids" not in out
    chunk_id = out["citations"][0]["chunk_id"]
    assert rag_srv.obtener_fragmento(chunk_id)["chunk_id"] == chunk_id
    assert rag_srv.obtener_fragmento("no-existe") == {"error": "no encontrado"}
    assert rag_srv.glosario("CSM")["encontrado"]


def test_risk_tools():
    assert risk_srv.clasificar_deudor("consumo_revolvente", 10)["categoria"] == "CPP"
    assert risk_srv.clasificar_deudor("consumo_revolvente", 99999)["error"]
    assert risk_srv.calcular_provision("microempresas", "Dudoso", 1000)["provision"] == "600.00"
    assert "error" in risk_srv.calcular_provision("microempresas", "Dudoso", 100, 500)


def test_servers_are_named():
    assert rag_srv.mcp.name == "rag-normativa"
    assert risk_srv.mcp.name == "riesgo-credito"
