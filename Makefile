.PHONY: install dev ingest ask api mcp-rag mcp-riesgo test lint eval security up down api-key docker

PY ?= python

install:
	$(PY) -m pip install -e ".[dev,mcp]"

ingest:
	$(PY) -m riskrag.cli ingest data/sample

ask:
	$(PY) -m riskrag.cli ask "$(Q)"

api:
	uvicorn riskrag.api.main:app --host 127.0.0.1 --port 8000 --reload

mcp-rag:
	$(PY) -m riskrag.mcp_servers.rag_normativa

mcp-riesgo:
	$(PY) -m riskrag.mcp_servers.riesgo_credito

test:
	$(PY) -m pytest --cov=riskrag --cov-report=term-missing

lint:
	ruff check src tests eval
	ruff format --check src tests eval

eval: ingest
	$(PY) -m eval.run_eval

security:
	pip-audit
	ruff check --select S src

up:
	docker compose up -d --build

down:
	docker compose down

docker:
	docker build -t riskrag:local .

api-key:
	@$(PY) -c "import secrets,hashlib; k=secrets.token_urlsafe(32); print('API key (guárdala):', k); print('SHA-256 (va en RISKRAG_API_KEYS_SHA256):', hashlib.sha256(k.encode()).hexdigest())"
