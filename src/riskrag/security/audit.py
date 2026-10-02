"""Registro de auditoría estructurado (JSON Lines).

Cada consulta, llamada a herramienta y decisión de seguridad deja una línea
con hora, evento, identidad (hash) y metadatos. El texto se enmascara antes
de escribirse para que los logs nunca contengan datos personales. En AWS el
mismo formato va a CloudWatch Logs con retención y cifrado KMS.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from riskrag.security.pii import mask_pii

_LOCK = threading.Lock()


def hash_identity(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class AuditLogger:
    def __init__(self, path: Path, echo_stdout: bool = False) -> None:
        self.path = path
        self.echo_stdout = echo_stdout  # en ECS stdout llega a CloudWatch y alimenta las alarmas
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, *, actor: str | None = None, **fields: Any) -> None:
        record: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "actor": hash_identity(actor),
        }
        for key, value in fields.items():
            record[key] = mask_pii(value)[0] if isinstance(value, str) else value
        line = json.dumps(record, ensure_ascii=False, default=str)
        with _LOCK:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            if self.echo_stdout:
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
