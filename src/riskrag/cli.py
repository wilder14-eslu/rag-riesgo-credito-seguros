"""Línea de comandos: ingest, ask, eval.

Ejemplos:
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
