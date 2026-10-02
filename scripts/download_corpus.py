"""Descarga el corpus oficial listado en configs/fuentes.yaml (fase 1).

Reglas de seguridad:
- Solo descarga URLs cuyo dominio está en ``dominios_permitidos``.
- Solo HTTPS, con tamaño máximo y tipo de contenido PDF.
- Calcula el SHA-256. Si el manifiesto ya tiene uno y no coincide, no guarda el archivo.
- Si el manifiesto no tiene hash, lo imprime para que lo revises y lo fijes.

Uso:
    python scripts/download_corpus.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "configs" / "fuentes.yaml"
DEST = ROOT / "data" / "raw"
MAX_BYTES = 50 * 1024 * 1024


def main() -> int:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    allowed = set(manifest.get("dominios_permitidos", []))
    DEST.mkdir(parents=True, exist_ok=True)
    status = 0
    for src in manifest.get("fuentes", []):
        name, url = src["archivo"], src.get("url")
        if not url or not name.lower().endswith(".pdf"):
            continue
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in allowed:
            print(f"[OMITIDO] {name}: URL no permitida ({url})")
            status = 1
            continue
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            print(f"[ERROR] {name}: HTTP {resp.status_code}")
            status = 1
            continue
        if len(resp.content) > MAX_BYTES or b"%PDF" not in resp.content[:1024]:
            print(f"[ERROR] {name}: el contenido no parece un PDF válido")
            status = 1
            continue
        digest = hashlib.sha256(resp.content).hexdigest()
        expected = src.get("sha256")
        if expected and expected != digest:
            print(f"[BLOQUEADO] {name}: el hash cambió. Esperado {expected}, recibido {digest}")
            status = 1
            continue
        (DEST / name).write_bytes(resp.content)
        note = "" if expected else "  <- revisa el documento y fija este sha256 en fuentes.yaml"
        print(f"[OK] {name} sha256={digest}{note}")
    return status


if __name__ == "__main__":
    sys.exit(main())
