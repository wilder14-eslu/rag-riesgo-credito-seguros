"""Script para empaquetar y construir el sitio estático para GitHub Pages.

Genera la carpeta `site/` con:
1. `riskrag_bundle.zip`: código de riskrag, configs y el índice pre-cargado.
2. `index.html`: interfaz Gradio-Lite (Pyodide en el navegador) con carga instantánea.
"""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
BUNDLE_ZIP = SITE_DIR / "riskrag_bundle.zip"
INDEX_HTML = SITE_DIR / "index.html"


def build_bundle() -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Empaquetar riskrag, configs y el índice en un zip ligero (~100 KB)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # Empaquetar src/riskrag como riskrag/
        src_riskrag = ROOT / "src" / "riskrag"
        for p in src_riskrag.rglob("*.py"):
            rel = p.relative_to(ROOT / "src")
            z.write(p, arcname=str(rel).replace("\\", "/"))

        # Empaquetar py.typed
        py_typed = src_riskrag / "py.typed"
        if py_typed.exists():
            z.write(py_typed, arcname="riskrag/py.typed")

        # Empaquetar configs/
        for p in (ROOT / "configs").rglob("*"):
            if p.is_file():
                rel = p.relative_to(ROOT)
                z.write(p, arcname=str(rel).replace("\\", "/"))

        # Empaquetar el índice pre-calculado data/processed/index.json
        index_file = ROOT / "data" / "processed" / "index.json"
        if index_file.exists():
            z.write(index_file, arcname="data/processed/index.json")
        else:
            raise FileNotFoundError(
                f"No se encontró el índice pre-procesado en {index_file}. Ejecuta 'riskrag ingest data/sample' primero."
            )

    BUNDLE_ZIP.write_bytes(buf.getvalue())
    print(f"Bundle generado: {BUNDLE_ZIP} ({BUNDLE_ZIP.stat().st_size / 1024:.1f} KB)")


def build_html() -> None:
    html_content = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RiskRAG · Demo en GitHub Pages</title>
  <link rel="icon" href="https://raw.githubusercontent.com/gradio-app/gradio/main/gradio/templates/frontend/assets/favicon.ico" />
  <script type="module" crossorigin src="https://cdn.jsdelivr.net/npm/@gradio/lite/dist/lite.js"></script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@gradio/lite/dist/lite.css" />
  <style>
    body {
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: #f8fafc;
      color: #0f172a;
    }
    .header-bar {
      background: #ffffff;
      border-bottom: 1px solid #e2e8f0;
      padding: 0.75rem 1.5rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .header-bar h1 {
      margin: 0;
      font-size: 1.15rem;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .badge {
      display: inline-block;
      background-color: #ecfdf5;
      color: #065f46;
      border: 1px solid #a7f3d0;
      border-radius: 9999px;
      padding: 0.15rem 0.55rem;
      font-size: 0.72rem;
      font-weight: 600;
    }
    .badge-gh {
      background-color: #eff6ff;
      color: #1e40af;
      border-color: #bfdbfe;
    }
    .container {
      max-width: 1080px;
      margin: 1.5rem auto;
      padding: 0 1rem;
    }
    gradio-lite {
      display: block;
      min-height: 700px;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
      background: #ffffff;
    }
  </style>
</head>
<body>
  <header class="header-bar">
    <h1>
      <span>RiskRAG</span>
      <span class="badge badge-gh">GitHub Pages</span>
      <span class="badge">0 Cold-Start · En Navegador</span>
    </h1>
    <a href="https://github.com/wilder14-eslu/rag-riesgo-credito-seguros" target="_blank" style="color: #2563eb; text-decoration: none; font-weight: 500; font-size: 0.9rem;">
      Ver código en GitHub &rarr;
    </a>
  </header>

  <main class="container">
    <gradio-lite theme="light">
      <gradio-requirements>
pydantic
pydantic-settings
pyyaml
snowballstemmer
numpy
      </gradio-requirements>
      <gradio-file name="app.py" entrypoint>
import os
import sys
import io
import zipfile
from pyodide.http import pyfetch

# Configurar variables de entorno antes de importar riskrag
os.environ["RISKRAG_ENV"] = "local"
os.environ["RISKRAG_PROJECT_ROOT"] = "."
os.environ["RISKRAG_INDEX_PATH"] = "data/processed/index.json"
os.environ["RISKRAG_AUDIT_LOG_PATH"] = "/tmp/audit.jsonl"
os.environ["RISKRAG_AUDIT_STDOUT"] = "false"
os.environ["RISKRAG_RATE_LIMIT_PER_MINUTE"] = "1000"

# 1. Descargar el bundle pre-cargado con código, configs e índice
resp = await pyfetch("riskrag_bundle.zip")
content = await resp.bytes()
with zipfile.ZipFile(io.BytesIO(content)) as z:
    z.extractall(".")

if "." not in sys.path:
    sys.path.insert(0, ".")

# 2. Inicializar servicios de RiskRAG con el índice pre-cargado
from riskrag.demo.handlers import DemoHandlers
from riskrag.factory import get_services
from riskrag.demo.app import build_demo

services = get_services()
handlers = DemoHandlers(services, per_minute=1000)

# 3. Lanzar la demo en Gradio-Lite
demo = build_demo(handlers)
demo.launch()
      </gradio-file>
    </gradio-lite>
  </main>
</body>
</html>
"""
    INDEX_HTML.write_text(html_content, encoding="utf-8")
    print(f"HTML generado: {INDEX_HTML} ({INDEX_HTML.stat().st_size / 1024:.1f} KB)")


def main() -> None:
    build_bundle()
    build_html()
    print("Sitio estático generado con éxito en site/")


if __name__ == "__main__":
    main()
