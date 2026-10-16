"""Línea de comandos: init-db, ingest, ask, eval.

Ejemplos:
    riskrag init-db
    riskrag ingest data/sample
    riskrag ask "¿Qué categoría corresponde a un crédito de consumo con 45 días de atraso?"
    riskrag eval
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def _cmd_init_db(args: argparse.Namespace) -> int:
    """Aplica los scripts de sql/ en orden (idempotentes). Lo usa el job de Container Apps."""
    import psycopg

    from riskrag.config import PROJECT_ROOT, get_settings

    settings = get_settings()
    if settings.pg_dsn is None:
        print("RISKRAG_PG_DSN no está definido.", file=sys.stderr)
        return 1
    scripts = sorted((Path(args.sql_dir) if args.sql_dir else PROJECT_ROOT / "sql").glob("*.sql"))
    with psycopg.connect(settings.pg_dsn.get_secret_value(), autocommit=True) as conn:
        for script in scripts:
            conn.execute(script.read_text(encoding="utf-8"))  # type: ignore[arg-type]
            print(f"Aplicado {script.name}")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from riskrag.factory import build_index

    report = build_index(Path(args.folder), use_manifest=not args.sin_manifiesto)
    print(json.dumps(report.__dict__, ensure_ascii=False, indent=2))
    return 0 if report.chunks else 1


def _cmd_ask(args: argparse.Namespace) -> int:
    from riskrag.agent.orchestrator import LocalAgent
    from riskrag.factory import get_services

    result = LocalAgent(get_services()).run(args.pregunta, actor="cli")
    print(f"Intención: {result.intent} | Herramienta: {result.tool}")
    print(result.answer.answer)
    for c in result.answer.citations:
        print(f"  - {c.label} ({c.source_url or 'sin url'})")
    if result.answer.security_flags:
        print(f"Señales de seguridad: {', '.join(result.answer.security_flags)}")
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from eval.run_eval import main as run_eval

    return run_eval(
        [
            "--dataset",
            args.dataset,
            "--adversarial",
            args.adversarial,
            "--thresholds",
            args.thresholds,
            "--output",
            args.output,
        ]
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="riskrag")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_db = sub.add_parser("init-db", help="Crear el esquema pgvector (scripts de sql/)")
    p_db.add_argument("--sql-dir", default=None)
    p_db.set_defaults(func=_cmd_init_db)

    p_ing = sub.add_parser("ingest", help="Ingerir e indexar una carpeta")
    p_ing.add_argument("folder")
    p_ing.add_argument(
        "--sin-manifiesto",
        action="store_true",
        help="Omitir el manifiesto de fuentes (solo desarrollo)",
    )
    p_ing.set_defaults(func=_cmd_ingest)

    p_ask = sub.add_parser("ask", help="Hacer una pregunta")
    p_ask.add_argument("pregunta")
    p_ask.set_defaults(func=_cmd_ask)

    p_eval = sub.add_parser("eval", help="Evaluar con los conjuntos de prueba")
    p_eval.add_argument("--dataset", default="eval/datasets/preguntas_base.jsonl")
    p_eval.add_argument("--adversarial", default="eval/datasets/adversarial.jsonl")
    p_eval.add_argument("--thresholds", default="eval/thresholds.yaml")
    p_eval.add_argument("--output", default="eval/reports/latest.json")
    p_eval.set_defaults(func=_cmd_eval)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
