"""Autenticación, límite de tasa y cabeceras de seguridad.

Dos formas de identificarse:

- **API key** (clientes programáticos): cabecera ``x-api-key``; el servicio
  solo guarda su hash SHA-256 y compara en tiempo constante.
- **Identidad firmada por el ALB** (usuarios humanos con Cognito): el ALB
  agrega ``x-amzn-oidc-data``, un JWT ES256 firmado con una clave de AWS. Se
  verifica la firma con la clave pública regional, que ``signer`` sea el ARN
  de nuestro ALB y que no esté vencido. Un atacante puede enviar esa cabecera,
  pero no puede firmarla.

En AWS la autenticación de usuarios la hace Cognito en el ALB y WAF aplica
límites por IP. Esta capa es la defensa en profundidad dentro del servicio:
si alguien llega al contenedor saltándose el ALB, igual necesita una API key.
Las claves se guardan solo como hash SHA-256 (Secrets Manager en AWS).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from collections.abc import Callable
from functools import lru_cache

import httpx
from fastapi import Depends, Header, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from riskrag.config import Settings, get_settings
from riskrag.security.ratelimit import RateLimiter

_limiter: RateLimiter | None = None
_KID_RE = re.compile(r"^[A-Za-z0-9-]{1,128}$")


@lru_cache(maxsize=32)
def fetch_alb_public_key(kid: str, region: str) -> str:  # pragma: no cover - requiere red de AWS
    if not _KID_RE.match(kid) or not re.match(r"^[a-z]{2}-[a-z]+-\d$", region):
        raise ValueError("kid o región inválidos")
    url = f"https://public-keys.auth.elb.{region}.amazonaws.com/{kid}"
    resp = httpx.get(url, timeout=5)
    resp.raise_for_status()
    return resp.text


def _b64json(segment: str) -> dict:
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def verify_alb_oidc(
    token: str,
    alb_arn: str | None,
    region: str,
    key_fetcher: Callable[[str, str], str] = fetch_alb_public_key,
) -> str | None:
    """Devuelve el ``sub`` del usuario si el JWT del ALB es válido; si no, None."""
    import jwt  # PyJWT, extra "aws"

    parts = token.split(".")
    if len(parts) != 3 or not alb_arn:
        return None
    try:
        header = _b64json(parts[0].rstrip("="))
    except (ValueError, json.JSONDecodeError):
        return None
    kid = str(header.get("kid", ""))
    if header.get("alg") != "ES256" or header.get("signer") != alb_arn or not _KID_RE.match(kid):
        return None
    try:
        public_key = key_fetcher(kid, region)
        # El ALB emite segmentos base64 con relleno "="; PyJWT espera base64url sin relleno
        clean = ".".join(p.rstrip("=") for p in parts)
        claims = jwt.decode(
            clean,
            public_key,
            algorithms=["ES256"],
            options={"require": ["exp", "sub"], "verify_aud": False},
        )
    except Exception:  # noqa: BLE001 - cualquier falla de verificación es un rechazo
        return None
    return str(claims["sub"])


def _get_limiter(settings: Settings) -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(settings.rate_limit_per_minute)
    return _limiter


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
    x_amzn_oidc_data: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    """Devuelve una identidad estable (hash corto) o falla con 401/429."""
    if settings.trust_alb_oidc and x_amzn_oidc_data and not x_api_key:
        sub = verify_alb_oidc(x_amzn_oidc_data, settings.alb_arn, settings.aws_region)
        if sub is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identidad no válida.")
        identity = f"oidc:{hashlib.sha256(sub.encode()).hexdigest()[:12]}"
    elif not settings.api_keys_sha256:
        if settings.env != "local":
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Servicio sin claves configuradas."
            )
        identity = f"local:{request.client.host if request.client else 'anon'}"
    else:
        if not x_api_key:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta la API key.")
        digest = hashlib.sha256(x_api_key.encode()).hexdigest()
        if not any(hmac.compare_digest(digest, k) for k in settings.api_keys_sha256):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key inválida.")
        identity = f"key:{digest[:12]}"
    if not _get_limiter(settings).allow(identity):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiadas solicitudes.")
    return identity


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response
