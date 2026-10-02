# Análisis del proyecto: RAG experto en riesgo crediticio y seguros

Fecha del análisis: 01/10/2026. Autor: Wilder Espinoza Luna.

## 1. Resumen ejecutivo

El proyecto construye un asistente que responde preguntas de riesgo crediticio y seguros con citas verificables a la norma, se abstiene cuando no tiene sustento, delega todo cálculo regulatorio a herramientas deterministas y expone sus capacidades como servidores MCP. Está pensado como pieza de portafolio de ML Engineering: el valor no está en "conectar un LLM a unos PDFs", sino en cuatro decisiones que un equipo de riesgos de un banco exigiría:

1. **Exactitud regulatoria antes que fluidez.** En este dominio una cifra mal citada (por ejemplo, un porcentaje de provisión) es peor que no responder. Por eso el sistema prefiere abstenerse, verifica cada oración contra su fuente y nunca deja que el LLM haga aritmética.
2. **Estructura legal como señal.** Las normas tienen capítulos, numerales y anexos con tablas. El chunking respeta esa jerarquía y cada fragmento conoce su ruta (`Capítulo II > Numeral 3`), vigencia y entidades.
3. **Seguridad por diseño.** Un RAG amplía la superficie de ataque: documentos que contienen instrucciones, herramientas con poder de acción y datos sensibles. El proyecto trata cada riesgo del OWASP Top 10 para LLM (edición 2025) con un control concreto y lo prueba con un conjunto adversario.
4. **Evaluación como puerta de calidad.** Cada cambio de chunking, modelo o prompt se mide contra el mismo conjunto de preguntas, y CI bloquea el merge si una métrica cae bajo su umbral.

Estado actual: el código completo funciona en modo local sin AWS (embeddings por hashing, índice en memoria, LLM extractivo) y en modo PostgreSQL + pgvector. Los backends de Bedrock están implementados y listos para activarse por configuración. Hay 71 pruebas automáticas (una de integración con PostgreSQL + pgvector) con 90% de cobertura y una evaluación de regresión con 8 métricas.

## 2. Problema y usuarios

| Usuario | Necesidad | Qué le da el sistema |
| --- | --- | --- |
| Analista de riesgos | Consultar rápido qué exige la norma para un caso | Respuesta con cita a capítulo y numeral, y cálculo determinista de clasificación o provisión |
| Auditor interno | Verificar que una respuesta tiene sustento | Cita navegable al fragmento, registro de auditoría y abstención explícita |
| Estudiante o postulante | Aprender el dominio (PD, LGD, IFRS 9, IFRS 17) | Glosario, explicaciones citadas y ejemplos de cálculo |
| Agente de IA (vía MCP) | Usar normativa y cálculos como herramientas | Servidores `rag-normativa` y `riesgo-credito` con entradas tipadas |

**Por qué un RAG y no solo un LLM.** Un modelo general conoce conceptos, pero no garantiza la versión vigente de una norma local ni puede citar el numeral exacto. El RAG ancla la respuesta en documentos aprobados y fechados.

**Por qué no solo búsqueda.** Un buscador devuelve documentos; el analista necesita la regla aplicada a su caso, con el cálculo y la excepción relevante.

## 3. Contexto regulatorio verificado

Se revisó el texto consolidado de la Resolución SBS N° 11356-2008 publicado por la SBS ([PDF oficial](https://www.sbs.gob.pe/portals/0/jer/pfrpv_normatividad/20160719_res-11356-2008.pdf)). Lo que el sistema usa en sus herramientas deterministas:

**Clasificación por días de atraso (Capítulo II):**

| Categoría | Pequeñas empresas, microempresas y consumo (numeral 3) | Hipotecarios para vivienda (numeral 4) |
| --- | --- | --- |
| Normal | hasta 8 días | hasta 30 días |
| CPP | 9 a 30 días | 31 a 60 días |
| Deficiente | 31 a 60 días | 61 a 120 días |
| Dudoso | 61 a 120 días | 121 a 365 días |
| Pérdida | más de 120 días | más de 365 días |

Para deudores no minoristas (corporativos, grandes y medianas empresas) la clasificación depende principalmente de la capacidad de pago, por lo que la herramienta se niega a clasificarlos solo por atraso. Es un ejemplo de diseño experto: la respuesta correcta a veces es "esto no se decide con un solo dato".

**Provisiones (Capítulo III, numeral 2.1):** genérica de 0.70% (corporativos, grandes empresas, hipotecarios) o 1.00% (resto) para la categoría Normal, y tres tablas de provisión específica:

| Categoría | Tabla 1 | Tabla 2 | Tabla 3 |
| --- | --- | --- | --- |
| CPP | 5.00% | 2.50% | 1.25% |
| Deficiente | 25.00% | 12.50% | 6.25% |
| Dudoso | 60.00% | 30.00% | 15.00% |
| Pérdida | 100.00% | 60.00% | 30.00% |

**Limitaciones declaradas:** la norma tiene modificaciones posteriores al texto consolidado revisado; la asignación de cada tabla según el tipo de garantía está marcada como pendiente de verificación en `configs/normativa/provisiones_sbs_11356_2008.yaml`; y el cálculo excluye el componente procíclico y los tratamientos especiales (refinanciados, reestructurados, reprogramaciones, alineamiento). Todo esto se muestra al usuario junto con cada cálculo.

## 4. Requisitos

### Funcionales

| Id | Requisito | Dónde se cumple |
| --- | --- | --- |
| RF1 | Responder preguntas normativas con cita a documento, capítulo y numeral | `generation/answer.py`, `generation/prompts.py` |
| RF2 | Abstenerse si la evidencia es débil o el modelo no encuentra sustento | Umbral `min_relevance`, token `NO_ENCONTRADO`, verificador |
| RF3 | Clasificar deudores y calcular provisiones de forma determinista | `tools/regulatory.py` |
| RF4 | Estimar probabilidad de default con el modelo de la plataforma de riesgo | `tools/credit_model.py` (contrato de `credit-risk-ml-platform`) |
| RF5 | Definir términos del dominio | `configs/glosario.yaml`, herramienta `glosario` |
| RF6 | Exponer todo como herramientas MCP | `mcp_servers/` |
| RF7 | Filtrar por vigencia de la norma | Metadatos `vigente_desde/hasta`, filtro en memoria y en SQL |

### No funcionales

| Atributo | Meta | Cómo se verifica |
| --- | --- | --- |
| Fidelidad | Mayor a 0.90 | Verificador por oración en el pipeline y en la evaluación |
| Recuperación | recall@5 mayor a 0.85 | `eval/run_eval.py` |
| Seguridad | Contener más del 95% de ataques del conjunto adversario | `eval/datasets/adversarial.jsonl` |
| Trazabilidad | Toda respuesta y llamada a herramienta queda auditada sin PII | `security/audit.py` |
| Reproducibilidad | Mismo resultado con misma entrada y versión de prompt | Temperatura 0, `PROMPT_VERSION`, tablas versionadas |
| Costo | Desarrollo y CI sin costo de nube | Backends locales por defecto |
| Portabilidad | Cambiar de proveedor sin reescribir | Interfaces `Embedder`, `VectorStore`, `LLM`, `Reranker`, `Guardrail` |

## 5. Arquitectura y decisiones clave

El detalle está en [02_arquitectura.md](02_arquitectura.md) y en los ADR. Las decisiones que más pesan:

| Decisión | Alternativa descartada | Motivo |
| --- | --- | --- |
| pgvector en Aurora como almacén por defecto ([ADR 0001](adr/0001-pgvector-por-defecto.md)) | OpenSearch Serverless | Menor costo base para un portafolio, SQL junto a vectores y aprovecha experiencia previa en SQL; OpenSearch queda como alternativa medible |
| Búsqueda híbrida con RRF ([ADR 0004](adr/0004-busqueda-hibrida-rrf.md)) | Solo vectorial | Los números de norma y artículo se pierden en embeddings; BM25 los conserva |
| Cálculos en herramientas deterministas ([ADR 0003](adr/0003-calculos-deterministas.md)) | Que el LLM calcule | Reproducibilidad y auditoría; el LLM se equivoca en aritmética |
| Dos servidores MCP separados ([ADR 0002](adr/0002-mcp-servidores-separados.md)) | Un servidor con todo | Aislar permisos: solo uno llama a sistemas externos |
| Chunking jerárquico por estructura legal ([ADR 0005](adr/0005-chunking-jerarquico.md)) | Ventanas fijas de tokens | No separar la regla de su excepción y poder citar el numeral |

## 6. NLP: dónde aporta y cómo se mide

El NLP no es decoración: cada técnica resuelve un fallo concreto de un RAG ingenuo. Detalle en [03_nlp.md](03_nlp.md).

| Fallo de un RAG ingenuo | Técnica | Métrica que la justifica |
| --- | --- | --- |
| La sigla "CPP" no aparece igual en la norma | Expansión con glosario | recall@5 |
| "11356-2008" se pierde en el embedding | BM25 con tokens numéricos preservados y stemming en español | recall@5, MRR |
| No se puede filtrar por norma o categoría | NER de norma, artículo, porcentaje, días y categoría | Precisión de filtros |
| El agente usa la herramienta equivocada | Clasificador de intención | Exactitud de intención |
| El modelo afirma cifras que no están en la fuente | Verificación por oración (léxica y NLI opcional) | Fidelidad |
| Datos personales en documentos o consultas | Detección de PII con reglas para Perú (DNI, RUC, CCI) | Casos adversarios de PII |

## 7. Seguridad

El modelo de amenazas completo (STRIDE + OWASP LLM 2025) está en [04_seguridad.md](04_seguridad.md). Lo esencial: hay controles en cinco capas (entrada, ingesta, generación, herramientas e infraestructura) y la regla de que **ninguna capa es suficiente sola**. Por ejemplo, la inyección indirecta se ataca con el manifiesto de fuentes aprobadas, la cuarentena de fragmentos sospechosos en la ingesta, la delimitación del contexto en el prompt, el guardrail de Bedrock y la verificación de citas en la salida.

## 8. Evaluación y resultados actuales

Resultados sobre el corpus de ejemplo (4 documentos, 33 fragmentos, 24 preguntas base y 12 adversarias), con backends locales:

| Métrica | Valor | Umbral |
| --- | --- | --- |
| recall@5 | 1.000 | 0.85 |
| MRR | 1.000 | 0.60 |
| Exactitud de intención | 0.917 | 0.85 |
| Cobertura de datos clave | 0.857 | 0.70 |
| Precisión de citas | 0.896 | 0.85 |
| Exactitud de abstención | 1.000 | 0.90 |
| Fidelidad | 1.000 | 0.90 |
| Contención adversaria | 1.000 | 0.95 |

**Cómo leer estos números.** Con un corpus tan pequeño la recuperación es casi trivial: estos valores prueban que el pipeline y las métricas funcionan, no la calidad final. La evaluación real ocurre en la fase 2 con el corpus oficial y 60 a 100 preguntas anotadas.

**Lo que la evaluación ya enseñó.** La primera corrida falló en tres métricas y cada falla reveló un defecto real que se corrigió:

1. La abstención no funcionaba: el reranker normalizaba por el mejor candidato del grupo, así que el primero siempre parecía relevante. Se cambió a normalizar por el máximo teórico de RRF.
2. La fidelidad salía 0.75 aunque las respuestas eran copias exactas: el verificador unía dos oraciones de fuentes distintas. Ahora una marca de cita cierra la afirmación.
3. Dos ataques pasaban (exfiltración a un webhook y pedido de lista de clientes con DNI). Se ajustaron las reglas y se propagan las señales de seguridad al resultado.

También apareció un trade-off medible: exigir que las oraciones elegidas estén cerca de la mejor (umbral relativo 0.85) subió la precisión de citas de 0.83 a 0.90 pero bajó la cobertura de datos clave de 0.95 a 0.86. Se eligió precisión porque en normativa una cita equivocada cuesta más que una respuesta incompleta. Detalle en [05_evaluacion.md](05_evaluacion.md).

## 9. Costos

En modo local el costo es cero. En AWS los componentes con costo base (que se paga aunque no haya tráfico) son Aurora Serverless v2 (capacidad mínima), los endpoints de interfaz de la VPC, el ALB y WAF. Los de costo variable son Bedrock (tokens de entrada y salida, embeddings, rerank) y CloudWatch. El proyecto incluye un presupuesto de AWS con alertas al 80% y 100%, y la recomendación de apagar el entorno `dev` entre sesiones. Los precios cambian por región y fecha, así que el cálculo se hace con la calculadora oficial de AWS antes de desplegar; ver [09_despliegue_aws.md](09_despliegue_aws.md).

## 10. Riesgos del proyecto

| Riesgo | Probabilidad | Impacto | Mitigación |
| --- | --- | --- | --- |
| Normas desactualizadas en el corpus | Alta | Alto | Metadatos de vigencia, fecha de verificación por tabla, manifiesto con hash |
| Tablas de anexos mal extraídas de PDF | Media | Alto | Tablas críticas transcritas a YAML versionado y probadas en bordes |
| Costo de AWS fuera de control | Media | Medio | Backends locales por defecto, presupuesto con alertas, apagar `dev` |
| Modelos no disponibles en la región | Media | Medio | IDs configurables y capa de modelos intercambiable |
| Falsa sensación de seguridad con reglas heurísticas | Media | Alto | Defensa en capas, guardrail de Bedrock, conjunto adversario que crece |
| Sobreajuste de umbrales al corpus de ejemplo | Alta | Medio | Recalibrar con el corpus oficial y separar preguntas de ajuste y de prueba |

## 11. Valor para el portafolio

Este proyecto conversa con los otros del portafolio: consume el modelo de default de `credit-risk-ml-platform` como herramienta MCP, aplica la misma disciplina estadística de evaluación (métricas con umbrales, reportes reproducibles) y agrega lo que piden las vacantes de ML Engineer y de analítica avanzada en banca y seguros: RAG con evaluación, agentes con herramientas, seguridad de LLM, MLOps e infraestructura como código en AWS.

Preguntas de entrevista que el proyecto permite responder con evidencia: por qué híbrido y no solo vectorial, cómo se mide la fidelidad, cómo se defiende de inyección indirecta, por qué el LLM no calcula provisiones, qué se sacrificó al subir la precisión de citas y cómo se controla el costo.

## 12. Próximos pasos

Ver [07_hoja_de_ruta.md](07_hoja_de_ruta.md). Lo inmediato: descargar el corpus oficial con `scripts/download_corpus.py`, fijar hashes, escribir las 60 a 100 preguntas de evaluación con respuesta de referencia y activar Bedrock para comparar embeddings y almacenes.
