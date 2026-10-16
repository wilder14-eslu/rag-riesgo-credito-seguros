---
title: RiskRAG
emoji: 🏦
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: RAG de riesgo crediticio con citas, abstención y guardrails
---

# RiskRAG · demo

Asistente RAG de normativa de riesgo crediticio y seguros que **cita el capítulo y numeral**, se **abstiene** cuando no tiene sustento, **calcula** clasificación y provisiones con herramientas deterministas y **bloquea** inyecciones de prompt.

Esta demo corre en **modo local**: embeddings por hashing, LLM extractivo y un corpus de ejemplo. La versión con Azure OpenAI, Azure AI Content Safety y Terraform está en el repositorio:
[github.com/wilder14-eslu/rag-riesgo-credito-seguros](https://github.com/wilder14-eslu/rag-riesgo-credito-seguros).

- Interfaz: `/demo`
- API (Swagger): `/docs`

Proyecto educativo y de portafolio. No constituye asesoría legal ni regulatoria.

Autor: Wilder Espinoza Luna.
