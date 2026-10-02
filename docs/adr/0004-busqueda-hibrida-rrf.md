# ADR 0004: búsqueda híbrida con Reciprocal Rank Fusion

Estado: aceptada (01/10/2026).

## Contexto
En normativa, la consulta suele contener identificadores exactos (número de resolución, numeral, porcentaje) que la búsqueda vectorial no distingue bien, y conceptos que BM25 no relaciona si se redactan distinto.

## Decisión
Recuperar candidatos densos y léxicos por separado y fusionarlos con RRF (k = 60), que combina rangos sin calibrar puntajes de distinta naturaleza. Luego aplicar un reranker. El puntaje final se normaliza con el máximo teórico de RRF para que sea comparable entre consultas y sirva para decidir la abstención.

## Consecuencias
- Robustez ante consultas con números y ante paráfrasis.
- Dos índices que mantener; en PostgreSQL ambos viven en la misma tabla.
- La normalización por máximo teórico corrigió un defecto real detectado por la evaluación (ver 05_evaluacion.md).
