# Hoja de ruta

Cinco fases de dos semanas, cada una con una puerta de calidad. No se avanza si la métrica de la puerta no se cumple. Las semanas son una estimación a ritmo parcial.

| Fase | Semanas | Entregables | Puerta |
| --- | --- | --- | --- |
| 1. Fundamentos | 1 a 2 | rsc-harness instalado; corpus oficial descargado con hash fijado; 60 preguntas anotadas; línea base local | Corpus verificado y conjunto de evaluación listo |
| 2. Recuperación | 3 a 4 | Bedrock embeddings; comparación pgvector vs OpenSearch; NER evaluado con F1; ajuste de chunking | recall@5 mayor a 0.85 en el conjunto de prueba |
| 3. Generación | 5 a 6 | Claude en Bedrock; guardrail de Bedrock; NLI opcional; RAGAS como segunda opinión | Fidelidad mayor a 0.90 y abstención mayor a 0.90 |
| 4. MCP y agente | 7 a 8 | Agente con herramientas en Bedrock; servidores MCP conectados a Claude Desktop; integración con `credit-risk-ml-platform` | Acierto de herramienta mayor a 90% |
| 5. Despliegue | 9 a 10 | Terraform aplicado en `dev`; CI completo; demo; README con resultados reales; costo medido | Contención adversaria mayor a 95% en el entorno desplegado |

## Estado al 01/10/2026

- [x] Código base completo con backends locales y de AWS
- [x] Ingesta con manifiesto, PII y cuarentena
- [x] Recuperación híbrida, rerank y abstención
- [x] Herramientas deterministas con tablas verificadas contra el PDF de la SBS
- [x] Servidores MCP probados por stdio
- [x] API con autenticación, límite de tasa y cabeceras de seguridad
- [x] Evaluación con 8 métricas y puertas en CI
- [x] Terraform de la infraestructura (falta `terraform validate` contra el proveedor)
- [ ] Corpus oficial descargado y hashes fijados
- [ ] 60 a 100 preguntas anotadas sobre el corpus oficial
- [ ] Activación y comparación de modelos en Bedrock
- [ ] Despliegue en AWS
