# Uso de rsc-harness

[rsc-harness](https://github.com/ericrisco/rsc-harness) es un meta-harness para agentes de código (Claude Code, Codex, Cursor, Copilot y otros): instala skills por proyecto, memoria de sesión y reglas deterministas. No es parte del sistema en producción; se usa para construir el proyecto con disciplina.

## Instalación

Dentro de la carpeta del proyecto:

```bash
npx @ericrisco/rsc
```

El asistente detecta el stack (encontrará `pyproject.toml` y `Dockerfile`), pregunta qué agentes usar y propone skills. Para este proyecto conviene elegir Claude Code y revisar las recomendaciones con:

```bash
rsc consult "rag fastapi aws terraform evaluacion"
```

Luego instalar solo las que aporten (los nombres exactos se confirman con `rsc consult`), por ejemplo las de RAG, embeddings, Python, FastAPI, Docker, GitHub Actions, AWS y Postgres.

## Cómo encaja con este repositorio

| Pieza de rsc | Uso aquí |
| --- | --- |
| Flujo SDD (`specify`, `plan`, `implement`, `verify`, `ship`) | Cada fase de la hoja de ruta empieza con una especificación corta antes de codificar |
| `02-DOCS/` | Wiki de aprendizajes: resultados de comparaciones, decisiones de chunking, ataques nuevos encontrados. Los ADR formales siguen en `docs/adr/` |
| `01-TOOLS/` | Conectores con prueba de conexión hacia Bedrock y la base |
| Hooks de Claude Code | Puerta de especificación y guía de mensajes de commit |

## Qué se versiona

Se versionan `.rsc.json`, `01-TOOLS/`, `02-DOCS/` y los skills propios. La carpeta `.rsc/` es estado local de la máquina y ya está en `.gitignore`.

## Límites

rsc no trae MCP de forma nativa ni conocimiento del dominio de riesgos: los servidores MCP y el corpus son de este proyecto.
