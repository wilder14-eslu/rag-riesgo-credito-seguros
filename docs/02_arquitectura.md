# Arquitectura

## Vista general

```mermaid
flowchart LR
    subgraph Ingesta[Ingesta offline]
        A[Fuentes aprobadas<br/>configs/fuentes.yaml] --> B[Carga y limpieza]
        B --> C[Enmascarado de PII]
        C --> D[Chunking jerárquico<br/>NER y referencias]
        D --> E{¿Inyección?}
        E -->|sí| Q[Cuarentena]
        E -->|no| F[Embeddings]
        F --> G[(Índice vectorial<br/>PostgreSQL + pgvector)]
    end

    subgraph Consulta[Consulta en línea]
        U[Cliente o agente MCP] --> V[Validación y guardrail de entrada<br/>reglas + Prompt Shields]
        V --> I[Intención]
        I -->|normativa| R[Recuperación híbrida<br/>denso + BM25 + RRF]
        R --> G
        R --> PS[Prompt Shields sobre<br/>documentos recuperados]
        PS --> K[Rerank y abstención]
        K --> L[LLM con citas]
        L --> O[Verificación, citas válidas<br/>y guardrail de salida]
        I -->|cálculo| T[Herramientas deterministas]
        I -->|predicción| M[Modelo de default<br/>credit-risk-ml-platform]
        I -->|glosario| GL[Glosario]
    end
```

## Componentes y responsabilidades

| Capa | Módulo | Responsabilidad |
| --- | --- | --- |
| Configuración | `config.py` | Variables `RISKRAG_*`; backends intercambiables |
| Ingesta | `ingest/loaders.py`, `ingest/manifest.py`, `ingest/legal_chunker.py`, `ingest/pipeline.py` | Cargar, validar contra el manifiesto, limpiar, enmascarar, segmentar, poner en cuarentena |
| NLP | `nlp/normalize.py`, `nlp/entities.py`, `nlp/intent.py`, `nlp/query_expansion.py`, `nlp/verifier.py` | Tokenización en español, NER, intención, expansión, verificación |
| Recuperación | `retrieval/embeddings.py`, `retrieval/bm25.py`, `retrieval/vector_store.py`, `retrieval/hybrid.py`, `retrieval/reranker.py` | Denso + léxico, fusión RRF, filtro de vigencia, rerank |
| Generación | `generation/prompts.py`, `generation/llm.py`, `generation/answer.py` | Prompt versionado, LLM, citas, abstención |
| Seguridad | `security/*` | Validación, PII, inyección, guardrails, auditoría, límite de tasa |
| Herramientas | `tools/regulatory.py`, `tools/credit_model.py` | Clasificación, provisiones, cliente del modelo de default |
| Agente | `agent/orchestrator.py` | Enrutamiento local y agente con function calling en Azure OpenAI |
| Interfaces | `api/main.py`, `mcp_servers/*`, `cli.py` | REST, MCP y línea de comandos |

## Backends por entorno

| Pieza | Local (por defecto) | Azure |
| --- | --- | --- |
| Embeddings | `HashingEmbedder` (sin costo, no semántico) | `text-embedding-3-large` en Azure OpenAI, reducido a 1024 dimensiones |
| Almacén | `InMemoryVectorStore` o pgvector en Docker | Azure Database for PostgreSQL Flexible Server con pgvector |
| LLM | `ExtractiveLLM` (no alucina, línea base) | `gpt-4.1-mini` en Azure OpenAI (Chat Completions) |
| Rerank | `LexicalReranker` | `LexicalReranker` u opcionalmente Cohere Rerank en Azure AI Foundry |
| Guardrail | Reglas locales | Reglas locales + Azure AI Content Safety (Prompt Shields y moderación) |
| Autenticación | API key | API key o token de Microsoft Entra ID con rol `RiskRAG.Query` |

## Despliegue en Azure

```mermaid
flowchart TB
    Internet --> AFD[Azure Front Door + WAF<br/>HTTPS, límite por IP]
    AFD --> CA
    subgraph VNet[VNet]
        subgraph Apps[Subred de Container Apps]
            CA[Container App: API<br/>identidad administrada, escala a cero]
            JOB[Job de ingesta<br/>init-db + ingest]
        end
        subgraph Datos[Subred delegada]
            DB[(PostgreSQL Flexible<br/>pgvector, sin acceso público)]
        end
        PE[Endpoints privados]
    end
    CA --> DB
    JOB --> DB
    CA --> PE
    JOB --> PE
    PE --> AOAI[Azure OpenAI<br/>GPT y embeddings]
    PE --> CS[Azure AI Content Safety<br/>Prompt Shields]
    PE --> KV[Key Vault<br/>DSN y hashes de API keys]
    ACR[Container Registry] -.imagen.-> CA
    CA --> LA[Log Analytics<br/>auditoría y alertas]
    ENTRA[Microsoft Entra ID] -.tokens.-> CA
```

La infraestructura está en `infra/terraform/` y se explica en [09_despliegue_azure.md](09_despliegue_azure.md). La decisión de usar Azure está en el [ADR 0006](adr/0006-azure-como-nube.md).

## Flujo de una consulta normativa

1. `sanitize_query` normaliza Unicode, quita caracteres invisibles y limita el tamaño.
2. El guardrail de entrada bloquea ataques (reglas locales y, en Azure, Prompt Shields) y enmascara PII.
3. La consulta léxica se expande con el glosario; la consulta densa queda igual.
4. Se recuperan 20 candidatos densos y 20 léxicos, ambos filtrados por vigencia y dominio.
5. Prompt Shields revisa los documentos recuperados y se descartan los que traen instrucciones ocultas. RRF fusiona los rankings; el reranker deja los 5 mejores con un puntaje comparable entre consultas.
6. Si el mejor puntaje está bajo `min_relevance`, se responde que no hay sustento.
7. El LLM recibe documentos delimitados, con id `C1..C5`, y la instrucción de tratarlos como datos.
8. Se eliminan citas inexistentes, se verifica cada oración y se aplica el guardrail de salida.
9. Se registra el evento de auditoría con la versión del prompt.
