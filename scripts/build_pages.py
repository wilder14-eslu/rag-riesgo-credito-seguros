"""Genera los datos que necesita la página estática (site/data/kb.json).

Descripción breve : Re-indexa el corpus de ejemplo y exporta chunks, vectores, glosario y tablas
                    SBS a un JSON que el navegador carga directamente (sin servidor).
Input             : data/sample/*.md, configs/glosario.yaml, configs/normativa/*.yaml
Output            : site/data/kb.json
Creado por        : Wilder Espinoza Luna

Uso:
    python scripts/build_pages.py            # re-indexa y exporta
    python scripts/build_pages.py --sin-ingesta   # solo exporta el índice ya existente
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from riskrag.config import get_settings
from riskrag.factory import build_index

ROOT = Path(__file__).resolve().parents[1]


def _stringify_floats(value):
    """Las tasas se exportan como texto ('5.0') para que el navegador haga aritmética decimal
    exacta y muestre lo mismo que Python (Decimal(str(float)))."""
    if isinstance(value, float):
        return str(value)
    if isinstance(value, dict):
        return {k: _stringify_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stringify_floats(v) for v in value]
    return value


def build(ingest: bool = True) -> dict:
    settings = get_settings()
    if ingest:
        report = build_index(ROOT / "data" / "sample", settings)
        print(
            f"Ingesta: {report.chunks} fragmentos, {len(report.quarantined_chunks)} en cuarentena"
        )

    payload = json.loads(settings.index_path.read_text(encoding="utf-8"))
    keep = (
        "chunk_id", "doc_id", "text", "article", "norm_id", "title", "source_url",
        "effective_from", "effective_to", "domain",
    )  # fmt: skip
    chunks = [{k: c.get(k) for k in keep} for c in payload["chunks"]]
    vectors = [[round(float(x), 6) for x in v] for v in payload["vectors"]]
    glossary = yaml.safe_load(settings.glossary_path.read_text(encoding="utf-8"))["terminos"]
    tables = _stringify_floats(yaml.safe_load(settings.provisions_path.read_text(encoding="utf-8")))

    eval_path = ROOT / "eval" / "reports" / "latest.json"
    report = json.loads(eval_path.read_text(encoding="utf-8")) if eval_path.is_file() else None

    return {
        "meta": {
            "dim": settings.embedding_dim,
            "min_relevance": settings.effective_min_relevance,
            "rrf_k": settings.rrf_k,
            "top_k_candidates": settings.top_k_candidates,
            "top_k_final": settings.top_k_final,
            "max_query_chars": settings.max_query_chars,
            "n_chunks": len(chunks),
            "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "eval": (
                {"metrics": report["metrics"], "thresholds": report["thresholds"]}
                if report
                else None
            ),
        },
        "chunks": chunks,
        "vectors": vectors,
        "glossary": glossary,
        "tables": tables,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sin-ingesta", action="store_true", help="No re-indexar el corpus")
    parser.add_argument("--out", type=Path, default=ROOT / "site" / "data" / "kb.json")
    args = parser.parse_args()
    kb = build(ingest=not args.sin_ingesta)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(kb, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size = args.out.stat().st_size / 1024
    print(f"OK: {args.out.relative_to(ROOT)} · {kb['meta']['n_chunks']} fragmentos · {size:.0f} KB")


if __name__ == "__main__":
    main()
