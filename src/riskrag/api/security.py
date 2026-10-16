"""Autenticación, límite de tasa y cabeceras de seguridad.

Dos formas de identificarse:

- **API key** (clientes programáticos simples): cabecera ``x-api-key``; el
  servicio solo guarda su hash SHA-256 y compara en tiempo constante.
- **Token de Microsoft Entra ID** (aplicaciones y usuarios de la organización):
  cabecera ``Authorization: Bearer <jwt>``. Se verifica la firma RS256 con las
  claves públicas del tenant, el emisor, la audiencia (la app registrada de la
  API), el vencimiento y que el token traiga el rol ``RiskRAG.Query``. Un
  atacante puede inventar un token, pero no firmarlo.

En Azure, Front Door con WAF aplica límites por IP delante del servicio y la
API solo acepta tráfico que trae el identificador de nuestra instancia de
Front Door (``X-Azure-FDID``). Esta capa es la defensa en profundidad dentro
del servicio: si alguien llega al contenedor saltándose Front Door, igual
necesita un token o una API key. Las claves se guardan solo como hash
SHA-256 (Key Vault en Azure).
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from riskrag.config import Settings, get_settings
from riskrag.security.ratelimit import RateLimiter

_limiter: RateLimiter | None = None
_TENANT_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
_BEARER_RE = re.compile(r"^Bearer\s+([A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)$")


@lru_cache(maxsize=4)
def _jwks_client(tenant_id: str) -> Any:  # pragma: no cover - requiere red de Microsoft
    import jwt

    if not _TENANT_RE.match(tenant_id):
        raise ValueError("tenant inválido")
    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=3600)


def fetch_entra_signing_key(token: str, tenant_id: str) -> Any:  # pragma: no cover - requiere red
    return _jwks_client(tenant_id).get_signing_key_from_jwt(token).key


def verify_entra_jwt(
    token: str,
    tenant_id: str | None,
    audience: str | None,
    required_role: str | None = "RiskRAG.Query",
    key_fetcher: Callable[[str, str], Any] = fetch_entra_signing_key,
) -> str | None:
    """Devuelve el ``oid`` (o ``sub``) si el token de Entra ID es válido; si no, None."""
    import jwt  # PyJWT, extra "azure"

    if not tenant_id or not audience or token.count(".") != 2:
        return None
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            return None
        claims = jwt.decode(
            token,
            key_fetcher(token, tenant_id),
            algorithms=["RS256"],
            audience=audience,
            issuer=f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except Exception:  # noqa: BLE001 - cualquier falla de verificación es un rechazo
        return None
    if claims.get("tid") != tenant_id:
        return None
    if required_role and required_role not in (claims.get("roles") or []):
        return None
    return str(claims.get("oid") or claims["sub"])


def _get_limiter(settings: Settings) -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter(settings.rate_limit_per_minute)
    return _limiter


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    """Devuelve una identidad estable (hash corto) o falla con 401/429."""
    if settings.trust_entra_jwt and authorization and not x_api_key:
        match = _BEARER_RE.match(authorization.strip())
        oid = (
            verify_entra_jwt(
                match.group(1),
                settings.entra_tenant_id,
                settings.entra_audience,
                settings.entra_required_role,
            )
            if match
            else None
        )
        if oid is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identidad no válida.")
        identity = f"entra:{hashlib.sha256(oid.encode()).hexdigest()[:12]}"
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


class FrontDoorOnlyMiddleware(BaseHTTPMiddleware):
    """Rechaza tráfico que no pasó por nuestra instancia de Azure Front Door.

    Front Door agrega ``X-Azure-FDID`` con el id de la instancia; otro cliente
    podría enviar la cabecera, pero no conoce el valor. ``/health`` queda libre
    para las sondas internas de Container Apps, que no pasan por Front Door.
    """

    def __init__(self, app: Any, front_door_id: str | None) -> None:
        super().__init__(app)
        self.front_door_id = front_door_id

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        if self.front_door_id and request.url.path != "/health":
            received = request.headers.get("x-azure-fdid", "")
            if not hmac.compare_digest(received.lower(), self.front_door_id.lower()):
                return JSONResponse(status_code=403, content={"detail": "Acceso no permitido."})
        return await call_next(request)


UI_PATHS = ("/docs", "/openapi.json", "/demo")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith(UI_PATHS):
            # Swagger y la demo cargan scripts y estilos; la demo se muestra dentro de
            # huggingface.co, así que solo ese sitio puede enmarcarla.
            response.headers["Content-Security-Policy"] = (
                "frame-ancestors 'self' https://huggingface.co"
            )
            return response
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response
