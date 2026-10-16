"""Credenciales para servicios de Azure AI.

En Azure Container Apps se usa la identidad administrada asignada por el
usuario (``AZURE_CLIENT_ID``), sin claves en el contenedor. En local o en
pruebas se puede usar una API key. ``azure-identity`` se importa solo si hace
falta, para que el modo local no dependa de Azure.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import SecretStr

COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


def token_provider(
    scope: str = COGNITIVE_SCOPE,
) -> Callable[[], str]:  # pragma: no cover - requiere Azure
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    return get_bearer_token_provider(DefaultAzureCredential(), scope)


def auth_headers(
    api_key: SecretStr | None,
    key_header: str = "api-key",
    provider: Callable[[], str] | None = None,
) -> dict[str, str]:
    """Cabecera de autenticación: la API key si existe; si no, un token de Entra ID."""
    if api_key is not None:
        return {key_header: api_key.get_secret_value()}
    provider = provider or token_provider()
    return {"Authorization": f"Bearer {provider()}"}
