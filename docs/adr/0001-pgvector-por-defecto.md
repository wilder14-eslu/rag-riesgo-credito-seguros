# ADR 0001: pgvector en PostgreSQL como almacén vectorial por defecto

Estado: aceptada (01/10/2026). Actualizada el 16/10/2026 con la migración a Azure ([ADR 0006](0006-azure-como-nube.md)). Revisión: tras la comparación de la fase 2.

## Contexto
Se necesita búsqueda vectorial con filtros por vigencia y dominio, y búsqueda léxica. Las opciones en Azure son Azure AI Search (búsqueda híbrida y reranker semántico administrados) y Azure Database for PostgreSQL Flexible Server con la extensión pgvector.

## Decisión
Usar PostgreSQL con pgvector como opción por defecto, con índice HNSW, texto completo en español (`tsvector`) y la función `rag.fnt_buscar_chunks_hibrido` para fusión RRF dentro de la base.

## Consecuencias
- Menor costo base para un proyecto de portafolio y una sola base para metadatos y vectores.
- Filtros por vigencia en SQL, con restricciones y auditoría propias de una base relacional.
- El mismo esquema corre en local (Docker), en CI y en Azure sin cambios.
- La búsqueda léxica de PostgreSQL es menos rica que la de Azure AI Search; la fase 2 mide si eso afecta recall@5.
- La interfaz `VectorStore` permite agregar Azure AI Search sin tocar el resto.
