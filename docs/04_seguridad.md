# Seguridad: modelo de amenazas y controles

La seguridad se trata como requisito medible. Cada amenaza tiene al menos un control implementado y, cuando es posible, una prueba automática o un caso en el conjunto adversario.

## Activos

| Activo | Por qué importa |
| --- | --- |
| Corpus e índice | Si se envenena, el sistema responde mal con apariencia de autoridad |
| Prompt del sistema y reglas | Su fuga facilita ataques dirigidos |
| Datos de solicitantes enviados al modelo de default | Datos personales y financieros |
| Credenciales (API keys, DSN de base, secretos de Azure) | Acceso a datos y costo |
| Registro de auditoría | Evidencia ante un incidente o auditoría |
| Presupuesto de nube | Un abuso puede generar costo alto |

## OWASP Top 10 para aplicaciones con LLM (2025)

| Riesgo | Cómo aparece aquí | Controles | Evidencia |
| --- | --- | --- | --- |
| LLM01 Inyección de prompt | Consultas que piden ignorar reglas; documentos con instrucciones ocultas | Detector de inyección en consultas y en la ingesta; cuarentena de fragmentos; contexto delimitado y declarado como dato; escape de etiquetas; Prompt Shields de Azure AI Content Safety sobre la pregunta y sobre cada documento recuperado (los marcados se descartan antes del LLM) | `test_injection_detected`, `test_ingest_quarantines_poisoned_chunks_and_masks_pii`, `test_documents_with_hidden_instructions_never_reach_llm`, casos a01 a a12 |
| LLM02 Divulgación de información sensible | PII en documentos, consultas o respuestas | Enmascarado de PII antes de indexar, en logs y en la salida; sin datos reales de clientes en la v1; filtros de PII del guardrail | `test_pii_masking`, caso a07 |
| LLM03 Cadena de suministro | Dependencias, imágenes o modelos comprometidos | Versiones fijadas; pip-audit, Trivy y gitleaks en CI; imagen mínima; modelos solo como despliegues de Azure OpenAI definidos en Terraform; la identidad de la app solo tiene el rol `Cognitive Services OpenAI User` | `.github/workflows/ci.yml` |
| LLM04 Envenenamiento de datos y modelos | Un PDF alterado o no oficial entra al índice | Manifiesto de fuentes aprobadas con dominio permitido y SHA-256; descarga solo HTTPS y PDF válido | `test_manifest_rejects_unlisted_and_tampered` |
| LLM05 Manejo inadecuado de la salida | El modelo inventa citas o emite contenido que otro sistema ejecuta | Solo se aceptan citas `[C#]` existentes; verificación de respaldo; la salida es texto, nunca se ejecuta; cabeceras de seguridad y CSP | `test_invented_citations_are_removed_and_abstains` |
| LLM06 Agencia excesiva | El agente llama herramientas no previstas o en bucle | Herramientas de solo lectura; lista permitida; esquemas tipados; máximo de pasos en el agente de Azure OpenAI; servidores MCP separados por permiso | `AzureOpenAIToolAgent.ALLOWED`, ADR 0002 |
| LLM07 Fuga del prompt del sistema | "Repite tus instrucciones" | Detector de fuga; regla en el prompt; métrica de fuga en la evaluación | casos a01, a03, a04, a05 |
| LLM08 Debilidades de vectores y embeddings | Fragmentos maliciosos que se recuperan por similitud; mezcla de datos entre clientes | Cuarentena en la ingesta; manifiesto; un solo inquilino por despliegue; filtros por dominio y vigencia en la consulta | `test_poisoned_chunk_not_indexed` |
| LLM09 Desinformación | Respuesta convincente pero falsa en un tema regulado | Citas obligatorias, abstención, verificador de cifras, normas con vigencia, aviso de que no es asesoría legal | Métricas de fidelidad y abstención |
| LLM10 Consumo sin límites | Consultas enormes o masivas que disparan costo | Límite de tamaño, límite de tasa en la app y en WAF, máximo de tokens, presupuesto con alertas | `test_ask_and_rate_limit`, `test_oversized_question_rejected` |

Referencia de la lista: [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/llm-top-10/).

## STRIDE sobre la arquitectura

| Amenaza | Ejemplo | Control |
| --- | --- | --- |
| Suplantación | Un cliente usa una API key robada, o alguien envía una cabecera de identidad falsa | Claves guardadas solo como hash; rotación vía Key Vault; tokens de Microsoft Entra ID verificados en la API (firma RS256 con las claves del tenant, emisor, audiencia, tenant, vencimiento y rol `RiskRAG.Query`); la API rechaza tráfico sin el `X-Azure-FDID` de nuestra instancia de Front Door |
| Manipulación | Alguien cambia un PDF del corpus | Bucket versionado, cifrado y solo TLS; hash en el manifiesto |
| Repudio | No se puede reconstruir qué respondió el sistema | Auditoría JSONL con versión de prompt y citas; logs cifrados con retención |
| Divulgación | Logs con datos personales | Enmascarado antes de escribir; identidad registrada como hash |
| Denegación de servicio | Ráfagas de consultas | WAF por IP, límite de tasa por identidad, autoescalado acotado |
| Elevación de privilegios | El contenedor comprometido accede a otros recursos | Usuario no root, sistema de archivos de solo lectura, capacidades eliminadas, IAM con modelos y recursos explícitos, red sin salida a internet |

## Defensa en capas contra la inyección indirecta

1. **Origen:** solo fuentes del manifiesto, de dominios oficiales y con hash.
2. **Ingesta:** cada fragmento pasa por el detector; los sospechosos van a cuarentena y se reportan.
3. **Prompt:** el contexto va entre etiquetas `<documento>`, con los signos `<` y `>` escapados, y la regla explícita de que es dato.
4. **Modelo:** Prompt Shields de Azure AI Content Safety, moderación de texto por severidad y el filtro de contenido propio de Azure OpenAI.
5. **Salida:** solo citas válidas; cada oración debe estar respaldada; si no, abstención.

## Límites conocidos

El detector local se basa en reglas y se puede evadir con paráfrasis, otros idiomas o codificaciones. Por eso no es la única barrera y el conjunto adversario debe crecer con cada ataque nuevo que se encuentre. El aviso de no asesoría legal no reemplaza la revisión humana en decisiones reales.

## Prácticas operativas

- Nunca subir `.env`, `terraform.tfvars` ni estados de Terraform (están en `.gitignore`).
- Los secretos se cargan en Secrets Manager fuera de Terraform.
- Rotar API keys con `make api-key` y actualizar el secreto.
- Revisar semanalmente la métrica `ConsultasBloqueadas` y las muestras de WAF.
