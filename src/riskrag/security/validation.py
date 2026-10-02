"""Validación de entradas (OWASP LLM10: consumo sin límites)."""

from __future__ import annotations

import re
import unicodedata

_CONTROL_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f​-‏‪-‮⁦-⁩]")


class InputRejected(ValueError):
    """La entrada no cumple las reglas y no se procesa."""


def sanitize_query(text: str, max_chars: int) -> str:
    """Normaliza Unicode, quita caracteres de control e invisibles y limita el tamaño.

    Los caracteres invisibles y de dirección (bidi) se usan para esconder
    instrucciones en texto aparentemente inocente.
    """
    if not isinstance(text, str):
        raise InputRejected("La consulta debe ser texto.")
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub("", text).strip()
    if not text:
        raise InputRejected("La consulta está vacía.")
    if len(text) > max_chars:
        raise InputRejected(f"La consulta supera {max_chars} caracteres.")
    return text
