"""Límite de tasa por identidad (token bucket en memoria).

Protege costo y disponibilidad (OWASP LLM10). En AWS el límite principal
vive en AWS WAF; este es el respaldo dentro de la aplicación.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, per_minute: int) -> None:
        self.capacity = float(per_minute)
        self.refill_per_s = per_minute / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_s)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            return True
