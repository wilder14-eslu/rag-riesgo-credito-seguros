# Despliegue en Azure

## Requisitos previos

1. Suscripción de Azure. Con [Azure for Students](https://azure.microsoft.com/free/students/) alcanza para un despliegue corto de `dev`.
2. Cuota de Azure OpenAI en la región elegida para el modelo de chat y el de embeddings (por defecto `gpt-4.1-mini` y `text-embedding-3-large`). Revisar en Azure AI Foundry que estén disponibles, su fecha de retiro y la cuota (miles de tokens por minuto) antes de aplicar.
3. Permiso en Microsoft Entra ID para crear registros de aplicaciones (en el directorio de una cuenta personal ya lo tienes).
4. Terraform 1.6 o superior y Azure CLI con sesión iniciada:
   ```bash
   az login
   az account set --subscription <id>
   ```

## Pasos

El registro de contenedores tiene que existir y tener la imagen antes de crear la Container App, por eso se aplica en dos partes.

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # completar valores (tu IP: curl -s https://ifconfig.me)
terraform init

# 1. Grupo de recursos y registro de contenedores
terraform apply -target=azurerm_container_registry.main

# 2. Construir la imagen en Azure (no hace falta Docker local) con un tag inmutable
ACR=$(terraform output -raw acr_login_server)
TAG=sha-$(git rev-parse --short HEAD)
az acr build --registry ${ACR%%.*} --image riskrag-api:$TAG ../..

# 3. Resto de la infraestructura con ese tag
terraform plan -var "container_image_tag=$TAG" -out plan.tfplan
terraform apply plan.tfplan
```

Después de aplicar:

1. **Esquema e índice:** ejecutar el job de ingesta, que corre `riskrag init-db` (scripts de `sql/`) y `riskrag ingest` sobre la carpeta `ingest_folder` incluida en la imagen:
   ```bash
   az containerapp job start -n $(terraform output -raw ingest_job_name) -g $(terraform output -raw resource_group)
   ```
2. **Probar con API key** (el hash va en `api_keys_sha256`; la clave en texto solo la tienes tú):
   ```bash
   curl -s $(terraform output -raw api_url)/v1/ask \
     -H "x-api-key: <tu clave>" -H "Content-Type: application/json" \
     -d '{"pregunta": "¿Qué categoría corresponde a un crédito de consumo con 45 días de atraso?"}'
   ```
3. **Probar con Microsoft Entra ID** (clientes de la organización): registrar una aplicación cliente, asignarle el rol `RiskRAG.Query` de la API y pedir un token con el scope `<entra_api_client_id>/.default` (flujo client credentials). La API valida firma, emisor, audiencia, tenant, vencimiento y rol.
4. **Corpus oficial:** descargar las normas con `scripts/download_corpus.py` a `data/raw/`, fijar sus hashes en `configs/fuentes.yaml`, reconstruir la imagen y ejecutar el job con `ingest_folder = "data/raw"`.

## Qué despliega Terraform

| Archivo | Recursos |
| --- | --- |
| `versions.tf` | Proveedores `azurerm`, `azuread` y `random`; grupo de recursos con etiquetas |
| `network.tf` | VNet con subred de Container Apps, subred delegada para PostgreSQL y subred de endpoints privados; NSG mínimos; zonas DNS privadas |
| `identity.tf` | Identidad administrada de la app con roles mínimos: `Cognitive Services OpenAI User`, `Cognitive Services User`, `Key Vault Secrets User` y `AcrPull` |
| `ai.tf` | Azure OpenAI y Content Safety sin claves (solo Entra ID), sin acceso público, con salida restringida y endpoints privados; despliegues de chat y embeddings |
| `database.tf` | PostgreSQL 16 Flexible Server integrado a la VNet, pgvector permitido, registro de conexiones |
| `secrets.tf` | Key Vault con RBAC, protección de purga, acceso público solo desde la IP del operador y endpoint privado; secretos del DSN y de los hashes de API keys con vencimiento |
| `registry.tf` | Azure Container Registry sin usuario administrador |
| `compute.tf` | Entorno de Container Apps en la VNet, API con escala a cero y sondas, job manual de ingesta |
| `frontdoor.tf` | Front Door con certificado administrado, solo HTTPS hacia el origen y WAF con límite por IP y tamaño de cuerpo (reglas OWASP y bots con el SKU Premium) |
| `auth.tf` | Registro de la API en Entra ID con el rol `RiskRAG.Query` y asignación obligatoria |
| `monitoring.tf` | Log Analytics con cuota diaria, diagnósticos de cada servicio, alertas de 5xx y de picos de bloqueos, presupuesto mensual |

## Diferencias con el diseño anterior en AWS

| Antes (AWS) | Ahora (Azure) | Nota |
| --- | --- | --- |
| Bedrock Guardrails | Content Safety + filtro de contenido de Azure OpenAI | Prompt Shields además revisa los documentos recuperados |
| Cognito en el ALB | Microsoft Entra ID verificado en la API | El token se valida dentro del servicio, no se confía en una cabecera |
| ALB + WAF | Front Door + WAF | La API exige el `X-Azure-FDID` de nuestra instancia |
| ECS Fargate con disco de solo lectura | Container Apps con `/tmp` efímero | Container Apps no ofrece sistema de archivos raíz de solo lectura; la imagen igual corre como usuario no root |
| KMS con clave propia | Claves administradas por Microsoft | CMK con Key Vault queda para prod |
| Bucket S3 del corpus | Corpus dentro de la imagen | Inmutable y verificado por hash en el manifiesto |

## Costos

Componentes con costo base: PostgreSQL Flexible Server B1ms, Front Door Standard, endpoints privados (por hora), registro de contenedores Basic y almacenamiento de la base. Componentes variables: tokens de Azure OpenAI, análisis de Content Safety y datos de Log Analytics (con techo de 1 GB al día). Container Apps escala a cero sin tráfico. Antes de aplicar, estimar con la [calculadora de precios de Azure](https://azure.microsoft.com/pricing/calculator/) en la región elegida. Para un portafolio:

- Destruir el entorno `dev` cuando no se use (`terraform destroy`). Key Vault queda en borrado temporal 7 días con protección de purga: para volver a crearlo con el mismo nombre se espera ese plazo o se cambia el sufijo.
- Usar backends locales para desarrollo y CI.
- Revisar el presupuesto y la alerta al 80%.

## Validación

El Terraform pasa `fmt` y `validate` contra `azurerm` 4.x y `azuread` 3.x, y Checkov no reporta hallazgos abiertos: las excepciones aceptadas por costo en `dev` están anotadas en el código con su justificación. El job `infraestructura` de CI repite estas revisiones en cada push.
