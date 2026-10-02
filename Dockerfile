# Imagen multi-etapa, usuario no root, sin herramientas de compilación en la final.
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --prefix=/install ".[aws,pg]"

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RISKRAG_PROJECT_ROOT=/app
# Aplica parches de seguridad del sistema publicados después de la imagen base
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /install /usr/local
COPY configs ./configs
COPY eval ./eval
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "riskrag.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
