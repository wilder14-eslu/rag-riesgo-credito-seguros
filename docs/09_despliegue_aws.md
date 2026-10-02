# Despliegue en AWS

## Requisitos previos

1. Cuenta de AWS con acceso habilitado en Bedrock a los modelos elegidos en la región (Claude, Titan Text Embeddings V2 o Cohere Embed, Cohere Rerank 3.5). Confirmar en la consola antes de aplicar.
2. Dominio propio y certificado en ACM para `app_domain`.
3. Terraform 1.6 o superior y AWS CLI configurado con un usuario o rol de despliegue (no la cuenta raíz).

## Pasos

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # completar valores
terraform init
terraform plan -out plan.tfplan
terraform apply plan.tfplan
```

Después de aplicar:

1. **Imagen:** construir y subir a ECR con un tag inmutable (por ejemplo el SHA del commit) y volver a aplicar con ese `container_image_tag`.
2. **Base de datos:** conectarse a Aurora con el secreto maestro que gestiona RDS, ejecutar `sql/001_crear_esquema_pgvector.sql` y `sql/002_fnt_buscar_chunks_hibrido.sql`, y crear un usuario de aplicación con el rol `riskrag_lectura` más permiso de escritura solo para el proceso de ingesta.
3. **Secretos:** cargar valores fuera de Terraform:
   ```bash
   aws secretsmanager put-secret-value --secret-id <secret_api_keys_arn> --secret-string '["<sha256>"]'
   aws secretsmanager put-secret-value --secret-id <secret_pg_dsn_arn> --secret-string 'host=... user=riskrag_app password=... dbname=riskrag sslmode=require'
   ```
4. **Corpus:** subir los PDF aprobados al bucket del corpus y ejecutar la ingesta como tarea puntual de ECS con `RISKRAG_EMBEDDER_BACKEND=bedrock` y `RISKRAG_VECTOR_BACKEND=pgvector`.
5. **DNS:** apuntar `app_domain` al `alb_dns_name`.
6. **Usuarios:** crear usuarios en Cognito (solo administradores pueden crearlos).

## Qué despliega Terraform

| Archivo | Recursos |
| --- | --- |
| `network.tf` | VPC sin NAT, subredes públicas y privadas, grupos de seguridad mínimos, endpoints privados, logs de flujo |
| `kms.tf` | Clave KMS con rotación |
| `storage.tf` | Bucket del corpus versionado, cifrado, privado y solo TLS |
| `database.tf` | Aurora PostgreSQL Serverless v2 cifrado, contraseña gestionada por RDS, autenticación IAM |
| `secrets.tf` | Secretos sin valor para API keys y DSN |
| `iam.tf` | Roles con mínimo privilegio y modelos de Bedrock explícitos |
| `compute.tf` | ECR inmutable con escaneo, ECS Fargate endurecido, ALB HTTPS con Cognito |
| `auth.tf` | Cognito con MFA y alta solo por administrador |
| `waf.tf` | Reglas administradas y límite de tasa por IP |
| `bedrock.tf` | Guardrail con ataques de prompt, PII de Perú, temas denegados y grounding |
| `monitoring.tf` | Logs cifrados, alarmas de 5xx y de bloqueos, presupuesto mensual |

## Costos

Componentes con costo base: Aurora (capacidad mínima), endpoints de interfaz (por hora y por zona), ALB, WAF y Cognito según uso. Componentes variables: tokens de Bedrock, embeddings, rerank, logs. Antes de aplicar, estimar con la calculadora de AWS en la región elegida. Para un portafolio:

- Mantener `enable_interface_endpoints` en `true` por seguridad, pero destruir el entorno `dev` cuando no se use (`terraform destroy`).
- Usar backends locales para desarrollo y CI.
- Revisar el presupuesto y la alarma al 80%.

## Modelos de Claude recientes

Los modelos de Claude más nuevos en Bedrock se invocan con un perfil de inferencia (por ejemplo un ID que empieza con `us.anthropic.`) en lugar del ID del modelo base. En ese caso: poner ese ID en `llm_model_id` y en `RISKRAG_BEDROCK_LLM_MODEL_ID`, y agregar en `extra_bedrock_resource_arns` el ARN del perfil y los ARN `foundation-model` de las regiones a las que enruta. El umbral de abstención con Cohere Rerank (`RISKRAG_MIN_RELEVANCE_BEDROCK_RERANK`) se recalibra en la fase 2 porque su escala es distinta a la del reranker léxico.

## Revisión independiente aplicada

Una revisión adversaria del código y del Terraform encontró, entre otros: permisos del rol de ejecución sobre el secreto equivocado (las tareas no habrían arrancado), reglas de grupo de seguridad en línea mezcladas con reglas separadas, falta de permiso KMS para que las alarmas publiquen en SNS, falta de salida 443 del ALB hacia Cognito, una opción de Cognito que requiere el plan PLUS, versiones del guardrail que no se republicaban, rutas de configuración que no existían dentro del contenedor, metadatos incompletos en pgvector que dejaban pasar normas derogadas por la rama léxica, un upsert que no actualizaba la vigencia, el guardrail de Bedrock tratando el enmascarado como bloqueo y la auditoría sin llegar a CloudWatch. Todos se corrigieron y los casos de lógica tienen pruebas (`tests/test_security_aws.py`, `tests/test_pgvector.py`).

## Validación pendiente

El código de Terraform pasó `fmt` y está escrito para el proveedor `hashicorp/aws` 5.x, pero en el entorno donde se generó no se pudo descargar el proveedor para ejecutar `terraform validate`. El job `infraestructura` de CI lo ejecuta en cada push; corregir ahí cualquier atributo que el proveedor rechace.
