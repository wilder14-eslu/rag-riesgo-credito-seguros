# ADR 0001: pgvector en Aurora como almacén vectorial por defecto

Estado: aceptada (01/10/2026). Revisión: tras la comparación de la fase 2.

## Contexto
Se necesita búsqueda vectorial con filtros por vigencia y dominio, y búsqueda léxica. Las opciones en AWS son OpenSearch Serverless y PostgreSQL con pgvector (Aurora o RDS).

## Decisión
Usar PostgreSQL con pgvector como opción por defecto, con índice HNSW, texto completo en español (`tsvector`) y la función `rag.fnt_buscar_chunks_hibrido` para fusión RRF dentro de la base.

## Consecuencias
- Menor costo base para un proyecto de portafolio y una sola base para metadatos y vectores.
- Filtros por vigencia en SQL, con restricciones y auditoría propias de una base relacional.
- La búsqueda léxica de PostgreSQL es menos rica que la de OpenSearch; la fase 2 mide si eso afecta recall@5.
- La interfaz `VectorStore` permite cambiar a OpenSearch sin tocar el resto.
