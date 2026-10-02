# NLP aplicado

Cada técnica de NLP del proyecto existe porque corrige un fallo concreto y tiene una métrica que la puede invalidar. Si una técnica no mejora su métrica, se quita.

## Pipeline

| Etapa | Técnica | Implementación | Métrica |
| --- | --- | --- | --- |
| Limpieza | Normalización Unicode, unión de palabras cortadas por guion de línea, guion suave de PDF | `nlp/normalize.py::clean_text` | Pruebas unitarias |
| Segmentación | Oraciones con protección de abreviaturas legales (Art., Res., N°) | `split_sentences` | Pruebas unitarias |
| Estructura | Detección de Título, Capítulo, Anexo, Artículo, Numeral y Subnumeral | `ingest/legal_chunker.py` | Precisión de la ruta citada |
| NER | Norma, ley, artículo, numeral, capítulo, anexo, porcentaje, días de atraso, fecha, categoría del deudor, tipo de crédito, métricas de riesgo | `nlp/entities.py` | F1 sobre fragmentos anotados (fase 2) |
| Referencias | Detección de "numeral 2.1 del Capítulo III" para un grafo de citas | `extract_cross_references` | Recall de artículos vinculados (fase 3) |
| Léxico | BM25 con stemming Snowball en español, sin tildes, stopwords, y tokens numéricos intactos | `nlp/normalize.py::tokenize`, `retrieval/bm25.py` | recall@5, MRR |
| Consulta | Expansión con glosario (siglas y sinónimos) solo en la rama léxica | `nlp/query_expansion.py` | recall@5 con y sin expansión |
| Intención | Reglas ponderadas: normativa, cálculo, predicción, glosario, fuera de dominio | `nlp/intent.py` | Exactitud de intención |
| Verificación | Cobertura léxica por oración y números idénticos a la fuente; NLI multilingüe opcional | `nlp/verifier.py` | Fidelidad |
| Privacidad | PII de Perú: DNI, RUC, CCI, tarjetas con Luhn, correos, celulares | `security/pii.py` | Casos adversarios de PII |

## Decisiones

**Números como tokens.** En normativa, "11356-2008", "0.70%" o "120 días" son la parte más informativa. El tokenizador no aplica stemming a tokens con dígitos y conserva separadores internos.

**Expansión solo léxica.** La consulta que va al embedding no se toca, porque agregar sinónimos desplaza el vector. La expansión solo ayuda a BM25, que sí se beneficia de más términos.

**Verificador estricto con cifras.** Una oración se considera respaldada si comparte al menos la mitad de sus términos con la fuente citada y si todos sus números aparecen en esa fuente. La prueba `test_unsupported_numbers_trigger_abstention` muestra que una cifra inventada (9.99%) provoca abstención aunque el resto de la oración coincida.

**Reglas primero, modelos después.** El NER y la intención empiezan con reglas explicables. En la fase 2 se compara contra modelos entrenados (spaCy con etiquetas propias, un clasificador TF-IDF o el propio LLM con uso de herramientas) y solo se reemplazan si mejoran la métrica.

## Extensiones previstas

| Extensión | Para qué | Dependencia |
| --- | --- | --- |
| NER entrenado con spaCy | Mejor recall en entidades con redacción variable | Extra `nlp` |
| NLI multilingüe (`NLIVerifier`) | Fidelidad semántica, no solo léxica | Extra `nlp` (transformers) |
| Presidio o Amazon Comprehend | Nombres de personas y direcciones | Extra `nlp` o AWS |
| Grafo de referencias cruzadas | Traer el artículo citado por el artículo recuperado | Fase 3 |
| Reescritura de consulta con LLM | Preguntas largas o ambiguas | Bedrock |
