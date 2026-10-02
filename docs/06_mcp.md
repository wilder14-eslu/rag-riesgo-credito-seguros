# Servidores MCP

El proyecto expone dos servidores con el SDK oficial de MCP para Python. Funcionan con la serie 1.x (`FastMCP`) y con la 2.x (`MCPServer`) gracias a `mcp_servers/_compat.py`. Se probó el arranque por stdio, el listado de herramientas y llamadas reales con un cliente MCP.

| Servidor | Herramienta | Entrada | Salida |
| --- | --- | --- | --- |
| `rag-normativa` | `buscar_normativa` | `pregunta`, `dominio` opcional | Respuesta con citas, abstención y señales de seguridad |
| `rag-normativa` | `obtener_fragmento` | `chunk_id` | Texto completo del fragmento citado con norma y vigencia |
| `rag-normativa` | `glosario` | `termino` | Definición y fuente |
| `riesgo-credito` | `clasificar_deudor` | `tipo_credito`, `dias_atraso` | Categoría, referencia normativa y fuente |
| `riesgo-credito` | `calcular_provision` | `tipo_credito`, `categoria`, `monto`, `monto_cubierto`, `garantia` | Provisión, detalle del cálculo y alcance |
| `riesgo-credito` | `predecir_default` | Datos del solicitante (contrato de `credit-risk-ml-platform`) | Probabilidad, decisión, banda de riesgo y factores |

## Por qué dos servidores

`rag-normativa` solo lee el índice. `riesgo-credito` puede llamar a un sistema externo (la API del modelo de default). Separarlos permite darles permisos, red y despliegue distintos, y que un cliente MCP habilite solo lo que necesita (ADR 0002).

## Uso con Claude Desktop

1. Instalar el proyecto en un entorno virtual: `pip install -e ".[mcp]"`.
2. Construir el índice: `python -m riskrag.cli ingest data/sample`.
3. Copiar `configs/claude_desktop_config.example.json` al archivo de configuración de Claude Desktop y ajustar la ruta al Python del entorno virtual.
4. Reiniciar Claude Desktop: las seis herramientas aparecen disponibles.

## Uso remoto

Con `RISKRAG_MCP_TRANSPORT=streamable-http` el servidor escucha por HTTP. Solo debe exponerse detrás del ALB con autenticación; por defecto se usa stdio, que no abre puertos.

## Probar con el inspector

```bash
mcp dev src/riskrag/mcp_servers/rag_normativa.py
```

## Seguridad de las herramientas

- Entradas tipadas: el SDK genera el JSON Schema desde las anotaciones (`Literal`, rangos con Pydantic).
- Validación extra de rangos y longitudes dentro de cada herramienta.
- Todas las llamadas quedan en el registro de auditoría.
- La respuesta de `predecir_default` se filtra a los campos esperados para no reenviar datos de más.
