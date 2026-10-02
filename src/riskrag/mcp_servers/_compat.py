"""Compatibilidad entre versiones del SDK oficial de MCP para Python.

La serie 1.x expone ``mcp.server.fastmcp.FastMCP``; versiones nuevas exponen
``mcp.server.MCPServer``. Ambas usan el mismo patrón de decoradores.
"""

from __future__ import annotations

import os


def create_server(name: str, instructions: str):  # type: ignore[no-untyped-def]
    try:
        from mcp.server.fastmcp import FastMCP

        return FastMCP(name, instructions=instructions)
    except ImportError:  # pragma: no cover
        from mcp.server import MCPServer

        return MCPServer(name, instructions=instructions)


def run_server(server) -> None:  # type: ignore[no-untyped-def]  # pragma: no cover
    """Por defecto stdio (local, sin red).

    El transporte HTTP no trae autenticación propia en este proyecto: solo se
    permite si se declara explícitamente que hay un proxy autenticado delante
    (``RISKRAG_MCP_HTTP_BEHIND_AUTH_PROXY=true``).
    """
    transport = os.getenv("RISKRAG_MCP_TRANSPORT", "stdio")
    if transport not in {"stdio", "streamable-http"}:
        raise ValueError("RISKRAG_MCP_TRANSPORT debe ser 'stdio' o 'streamable-http'")
    if (
        transport == "streamable-http"
        and os.getenv("RISKRAG_MCP_HTTP_BEHIND_AUTH_PROXY", "").lower() != "true"
    ):
        raise RuntimeError(
            "streamable-http requiere un proxy con autenticación delante. "
            "Define RISKRAG_MCP_HTTP_BEHIND_AUTH_PROXY=true solo si lo hay."
        )
    server.run(transport=transport)
