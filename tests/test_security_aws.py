"""Lógica de seguridad que se activa en AWS, probada sin AWS (clientes falsos y claves locales)."""

import base64
import json
import time

import pytest

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from riskrag.api.security import verify_alb_oidc  # noqa: E402
from riskrag.security.audit import AuditLogger  # noqa: E402
from riskrag.security.guardrails import BedrockGuardrail  # noqa: E402

ALB_ARN = "arn:aws:elasticloadbalancing:us-east-1:111111111111:loadbalancer/app/riskrag-dev/abc"


class FakeBedrock:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def apply_guardrail(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_bedrock_anonymize_only_is_allowed():
    client = FakeBedrock(
        {
            "action": "GUARDRAIL_INTERVENED",
            "outputs": [{"text": "Hola {NAME}"}],
            "assessments": [
                {
                    "sensitiveInformationPolicy": {
                        "piiEntities": [{"type": "NAME", "action": "ANONYMIZED"}]
                    }
                }
            ],
        }
    )
    g = BedrockGuardrail("gid", "1", "us-east-1", client=client)
    out = g.check("Hola Juan", "INPUT")
    assert out.allowed and out.text == "Hola {NAME}" and "bedrock:anonymized" in out.flags


def test_bedrock_blocked_is_rejected():
    client = FakeBedrock(
        {
            "action": "GUARDRAIL_INTERVENED",
            "outputs": [{"text": "Bloqueado"}],
            "assessments": [
                {"contentPolicy": {"filters": [{"type": "PROMPT_ATTACK", "action": "BLOCKED"}]}}
            ],
        }
    )
    out = BedrockGuardrail("gid", "1", "us-east-1", client=client).check("texto", "INPUT")
    assert not out.allowed and "bedrock:blocked" in out.flags


def test_bedrock_output_sends_grounding_qualifiers():
    client = FakeBedrock({"action": "NONE", "outputs": [], "assessments": []})
    g = BedrockGuardrail("gid", "1", "us-east-1", client=client)
    assert g.check("respuesta", "OUTPUT", query="pregunta", evidence=["fuente"]).allowed
    qualifiers = [c["text"]["qualifiers"][0] for c in client.calls[0]["content"]]
    assert qualifiers == ["grounding_source", "query", "guard_content"]


def _alb_token(private_key, signer=ALB_ARN, exp_delta=300, pad=True):
    """Simula el formato del ALB: segmentos base64 con relleno '='."""
    token = jwt.encode(
        {"sub": "user-123", "exp": int(time.time()) + exp_delta},
        private_key,
        algorithm="ES256",
        headers={"kid": "kid-1", "signer": signer},
    )
    if not pad:
        return token
    return ".".join(p + "=" * (-len(p) % 4) for p in token.split("."))


@pytest.fixture(scope="module")
def keypair():
    private = ec.generate_private_key(ec.SECP256R1())
    public_pem = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private, public_pem


def test_alb_oidc_valid_token(keypair):
    private, public_pem = keypair
    sub = verify_alb_oidc(
        _alb_token(private), ALB_ARN, "us-east-1", key_fetcher=lambda k, r: public_pem
    )
    assert sub == "user-123"


def test_alb_oidc_rejects_wrong_signer_expired_and_forged(keypair):
    private, public_pem = keypair
    fetch = lambda k, r: public_pem  # noqa: E731
    assert (
        verify_alb_oidc(_alb_token(private, signer="arn:otro"), ALB_ARN, "us-east-1", fetch) is None
    )
    assert verify_alb_oidc(_alb_token(private, exp_delta=-60), ALB_ARN, "us-east-1", fetch) is None
    other = ec.generate_private_key(ec.SECP256R1())
    assert verify_alb_oidc(_alb_token(other), ALB_ARN, "us-east-1", fetch) is None
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "signer": ALB_ARN, "kid": "k"}).encode()
    )
    assert verify_alb_oidc(header.decode() + ".e30.", ALB_ARN, "us-east-1", fetch) is None


def test_audit_echo_stdout(tmp_path, capsys):
    AuditLogger(tmp_path / "a.jsonl", echo_stdout=True).log(
        "query_blocked", actor="x", q="DNI: 12345678"
    )
    line = json.loads(capsys.readouterr().out.strip())
    assert line["event"] == "query_blocked" and "12345678" not in line["q"]
