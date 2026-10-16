# ADR 0006: Azure como nube de despliegue

Estado: aceptada (16/10/2026). Reemplaza el diseño inicial en AWS, que nunca se desplegó.

## Contexto
El proyecto se diseñó primero para AWS (Bedrock, Aurora, ECS Fargate, Cognito). Los bancos y aseguradoras a los que apunta este portafolio trabajan con Azure, y una infraestructura en la nube que el equipo ya usa se evalúa mejor que una en otra nube. El código ya separaba cada servicio externo detrás de una interfaz (LLM, embeddings, rerank, guardrail, almacén), así que el cambio afecta a los adaptadores y a la infraestructura, no al núcleo.

## Decisión
Desplegar solo en Azure:

| Pieza | Servicio |
| --- | --- |
| LLM y embeddings | Azure OpenAI (`gpt-4.1-mini`, `text-embedding-3-large` a 1024 dimensiones) |
| Guardrails | Azure AI Content Safety: Prompt Shields (ataques directos e indirectos) y moderación de texto |
| Almacén | Azure Database for PostgreSQL Flexible Server con pgvector, integrado a la VNet |
| Cómputo | Azure Container Apps (API que escala a cero y job manual de ingesta) |
| Entrada | Azure Front Door con WAF (límite por IP; reglas OWASP con el SKU Premium) |
| Identidad | Microsoft Entra ID (tokens con rol `RiskRAG.Query`) e identidad administrada para la app |
| Secretos | Key Vault con RBAC |
| Observabilidad | Log Analytics, alertas de Azure Monitor y presupuesto |

Se eligió Azure OpenAI sobre Claude en Azure AI Foundry porque es el servicio de LLM más usado en banca con Azure y se integra con el filtro de contenido y la identidad administrada sin pasos extra.

## Consecuencias
- Sin claves en el contenedor: la app usa su identidad administrada para Azure OpenAI, Content Safety, Key Vault y el registro de imágenes.
- Los servicios de IA y la base no tienen acceso público; Container Apps los alcanza por la VNet y zonas DNS privadas.
- El corpus viaja dentro de la imagen (inmutable y con hash en el manifiesto), por eso no hay cuenta de almacenamiento.
- Prompt Shields revisa también los documentos recuperados en cada consulta: es una segunda barrera contra la inyección indirecta además de la cuarentena de la ingesta.
- Decisiones de costo aceptadas para `dev` y documentadas en el Terraform: claves administradas por Microsoft en lugar de CMK, registro Basic (Trivy en CI cumple el escaneo), respaldo de PostgreSQL sin geo-redundancia y Front Door Standard sin reglas administradas. En prod se cambian por variables.
- Rerank con Cohere en Azure AI Foundry queda opcional (no está en Terraform); por defecto se usa el reranker léxico.
