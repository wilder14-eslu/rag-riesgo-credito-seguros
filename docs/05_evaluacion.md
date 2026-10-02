# Evaluación

## Métricas

| Métrica | Qué mide | Cálculo |
| --- | --- | --- |
| recall@5 | ¿Llegó la sección correcta al top 5? | Proporción de fuentes esperadas presentes en los 5 primeros |
| MRR | ¿Qué tan arriba está la primera fuente correcta? | Promedio de 1 / rango |
| Exactitud de intención | ¿Se eligió la ruta correcta? | Intención predicha igual a la anotada |
| Cobertura de datos clave | ¿La respuesta contiene los datos esenciales? | Proporción de `datos_clave` presentes en la respuesta |
| Precisión de citas | ¿Las citas apuntan a la sección correcta? | Proporción de citas que coinciden con alguna fuente esperada |
| Exactitud de abstención | ¿Se abstuvo cuando debía y respondió cuando podía? | Coincidencia con `debe_abstenerse` |
| Fidelidad | ¿Cada oración está respaldada? | 1 menos oraciones no respaldadas sobre el total |
| Contención adversaria | ¿Resistió los ataques? | Sin fuga de prompt, sin PII y bloqueo o abstención donde corresponde |

Los umbrales están en `eval/thresholds.yaml` y CI falla si alguna métrica queda por debajo.

## Formato del conjunto de prueba

```json
{"id": "q04", "pregunta": "¿Qué tasa de provisión genérica aplica a los créditos hipotecarios para vivienda?",
 "intencion": "normativa", "fuentes_esperadas": ["ejemplo-res-sbs-11356-2008|Capítulo III > Numeral 2.1"],
 "datos_clave": ["0.70%"], "debe_abstenerse": false}
```

`fuentes_esperadas` usa `doc_id|ruta`, y la ruta es un prefijo de la sección del fragmento. Así la métrica no depende del tamaño de los chunks.

## Resultados actuales (corpus de ejemplo, backends locales)

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

El corpus de ejemplo tiene 33 fragmentos: la recuperación casi perfecta no dice nada de la calidad con el corpus real. Lo que sí prueba es que el pipeline, las métricas y las puertas funcionan.

## Historial de hallazgos

| Corrida | Métricas en falla | Causa encontrada | Corrección |
| --- | --- | --- | --- |
| 1 | Precisión de citas 0.55, fidelidad 0.75, contención 0.92 | El reranker normalizaba por el mejor candidato del grupo; el verificador unía oraciones de fuentes distintas; dos ataques no se detectaban | Normalizar RRF por su máximo teórico; cerrar la afirmación en cada cita; reglas de exfiltración, volcado de datos y fuga de reglas |
| 2 | Precisión de citas 0.83 | El LLM extractivo agregaba oraciones de secciones vecinas | Umbral relativo: solo oraciones con al menos 85% del puntaje de la mejor |
| 3 | Ninguna | | Trade-off aceptado: cobertura de datos clave bajó de 0.95 a 0.86 a cambio de citas más precisas |

## Protocolo para la fase 2

1. Escribir de 60 a 100 preguntas sobre el corpus oficial, con respuesta de referencia y sección fuente. Incluir preguntas con norma derogada, sin respuesta y con premisa falsa.
2. Separar 30% como conjunto de ajuste y 70% como conjunto de prueba; los umbrales se calibran solo con el de ajuste.
3. Comparar, con el mismo conjunto: embeddings Titan V2 frente a Cohere Multilingual v3; pgvector frente a OpenSearch; con y sin expansión de glosario; con y sin rerank.
4. Reportar intervalos de confianza por bootstrap para recall@5 y fidelidad, porque con 100 preguntas una diferencia de 2 puntos puede ser ruido.
5. Con Bedrock activo, sumar las métricas de RAGAS (faithfulness, answer relevancy, context precision) como segunda opinión, sin reemplazar las métricas propias.
