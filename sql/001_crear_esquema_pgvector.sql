/*
================================================================================
Descripción breve : Crea el esquema "rag" con la tabla de fragmentos (chunks), su
                    vector de embedding y los índices para búsqueda vectorial,
                    léxica (texto completo en español) y por vigencia.
Input             : Ninguno. Requiere PostgreSQL 15+ con la extensión pgvector.
Output            : Esquema rag, tabla rag.chunk e índices.
Creado por        : Alex Espinoza
Fec Creación      : 01/10/2026
Fec Actualización : 01/10/2026
Responsable       : Wilder Espinoza Luna
Motivo            : Versión inicial del almacén vectorial del RAG de riesgo crediticio.
--------------------------------------------------------------------------------
Historial:
  01/10/2026  Alex Espinoza  Creación inicial.
================================================================================
*/

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.chunk (
    chunk_id          TEXT PRIMARY KEY,
    doc_id            TEXT        NOT NULL,
    texto             TEXT        NOT NULL,
    texto_padre       TEXT,
    ruta_seccion      TEXT[]      NOT NULL DEFAULT '{}',
    articulo          TEXT,
    norma             TEXT,
    titulo            TEXT,
    url_fuente        TEXT,
    vigente_desde     DATE,
    vigente_hasta     DATE,
    dominio           TEXT        NOT NULL DEFAULT 'general',
    entidades         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    referencias       TEXT[]      NOT NULL DEFAULT '{}',
    sintetico         BOOLEAN     NOT NULL DEFAULT FALSE,
    embedding         VECTOR(1024) NOT NULL,
    texto_busqueda    TSVECTOR GENERATED ALWAYS AS (to_tsvector('spanish', texto)) STORED,
    -- Campos de auditoría
    fec_creacion      TIMESTAMPTZ NOT NULL DEFAULT now(),
    fec_actualizacion TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_chunk_vigencia CHECK (vigente_hasta IS NULL OR vigente_desde IS NULL
                                        OR vigente_hasta >= vigente_desde)
);

-- Búsqueda vectorial aproximada (distancia coseno)
CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw
    ON rag.chunk USING hnsw (embedding vector_cosine_ops);

-- Búsqueda léxica en español
CREATE INDEX IF NOT EXISTS ix_chunk_texto_busqueda
    ON rag.chunk USING gin (texto_busqueda);

-- Filtros frecuentes
CREATE INDEX IF NOT EXISTS ix_chunk_vigencia ON rag.chunk (vigente_desde, vigente_hasta);
CREATE INDEX IF NOT EXISTS ix_chunk_dominio  ON rag.chunk (dominio);
CREATE INDEX IF NOT EXISTS ix_chunk_doc      ON rag.chunk (doc_id);

-- Rol de solo lectura para el servicio de consulta (mínimo privilegio)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'riskrag_lectura') THEN
        CREATE ROLE riskrag_lectura NOLOGIN;
    END IF;
END
$$;
GRANT USAGE ON SCHEMA rag TO riskrag_lectura;
GRANT SELECT ON ALL TABLES IN SCHEMA rag TO riskrag_lectura;
