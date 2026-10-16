# Imagen de la demo para Hugging Face Spaces (SDK Docker). Modo local: sin Azure y sin costo.
# El workflow deploy-space.yml la copia como Dockerfile en la raíz del Space.
FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Spaces ejecuta el contenedor con el usuario 1000
RUN useradd --create-home --uid 1000 user
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[demo]"

COPY configs ./configs
COPY data/sample ./data/sample

ENV RISKRAG_PROJECT_ROOT=/app \
    RISKRAG_ENV=local \
    RISKRAG_HOME_PATH=/demo \
    RISKRAG_INDEX_PATH=/tmp/riskrag/index.json \
    RISKRAG_AUDIT_LOG_PATH=/tmp/audit/audit.jsonl \
    RISKRAG_AUDIT_STDOUT=true \
    RISKRAG_RATE_LIMIT_PER_MINUTE=20 \
    FORWARDED_ALLOW_IPS="*" \
    GRADIO_ANALYTICS_ENABLED=False

USER user
EXPOSE 7860

# El índice se construye al arrancar (unos segundos) y luego se sirve la API con la demo en /demo
CMD ["sh", "-c", "python -m riskrag.cli ingest data/sample && exec uvicorn riskrag.demo.app:app --host 0.0.0.0 --port 7860 --proxy-headers --no-server-header"]
