# Azure Container Apps: la API (escala a cero sin tráfico) y un job manual de ingesta.

resource "azurerm_container_app_environment" "main" {
  name                           = "cae-${local.name}"
  location                       = azurerm_resource_group.main.location
  resource_group_name            = azurerm_resource_group.main.name
  log_analytics_workspace_id     = azurerm_log_analytics_workspace.main.id
  infrastructure_subnet_id       = azurerm_subnet.apps.id
  internal_load_balancer_enabled = false # el tráfico público entra por Front Door
  tags                           = local.tags

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

locals {
  image = "${azurerm_container_registry.main.login_server}/riskrag-api:${var.container_image_tag}"

  # Variables comunes de la API y del job de ingesta
  app_env = {
    RISKRAG_ENV                           = var.environment == "prod" ? "prod" : "dev"
    RISKRAG_EMBEDDER_BACKEND              = "azure_openai"
    RISKRAG_VECTOR_BACKEND                = "pgvector"
    RISKRAG_LLM_BACKEND                   = "azure_openai"
    RISKRAG_RERANKER_BACKEND              = "lexical"
    RISKRAG_GUARDRAIL_BACKEND             = "azure_content_safety"
    RISKRAG_AZURE_OPENAI_ENDPOINT         = azurerm_cognitive_account.openai.endpoint
    RISKRAG_AZURE_OPENAI_CHAT_DEPLOYMENT  = azurerm_cognitive_deployment.chat.name
    RISKRAG_AZURE_OPENAI_EMBED_DEPLOYMENT = azurerm_cognitive_deployment.embedding.name
    RISKRAG_AZURE_CONTENT_SAFETY_ENDPOINT = azurerm_cognitive_account.content_safety.endpoint
    RISKRAG_AUDIT_LOG_PATH                = "/tmp/audit/audit.jsonl"
    RISKRAG_AUDIT_STDOUT                  = "true"
    RISKRAG_PROJECT_ROOT                  = "/app"
    RISKRAG_TRUST_ENTRA_JWT               = "true"
    RISKRAG_ENTRA_TENANT_ID               = data.azurerm_client_config.current.tenant_id
    RISKRAG_ENTRA_AUDIENCE                = azuread_application.api.client_id
    RISKRAG_FRONT_DOOR_ID                 = azurerm_cdn_frontdoor_profile.main.resource_guid
    AZURE_CLIENT_ID                       = azurerm_user_assigned_identity.app.client_id # identidad para DefaultAzureCredential
  }
}

resource "azurerm_container_app" "api" {
  name                         = "ca-${local.name}-api"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "pg-dsn"
    key_vault_secret_id = azurerm_key_vault_secret.pg_dsn.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "api-keys-sha256"
    key_vault_secret_id = azurerm_key_vault_secret.api_keys.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  ingress {
    external_enabled           = true
    target_port                = 8000
    transport                  = "auto"
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0
    max_replicas = var.max_replicas

    volume {
      name         = "tmp"
      storage_type = "EmptyDir"
    }

    container {
      name   = "api"
      image  = local.image
      cpu    = 0.5
      memory = "1Gi"

      dynamic "env" {
        for_each = local.app_env
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name        = "RISKRAG_PG_DSN"
        secret_name = "pg-dsn"
      }

      env {
        name        = "RISKRAG_API_KEYS_SHA256"
        secret_name = "api-keys-sha256"
      }

      volume_mounts {
        name = "tmp"
        path = "/tmp"
      }

      liveness_probe {
        transport        = "HTTP"
        path             = "/health"
        port             = 8000
        initial_delay    = 10
        interval_seconds = 30
      }

      readiness_probe {
        transport        = "HTTP"
        path             = "/health"
        port             = 8000
        interval_seconds = 10
      }
    }

    http_scale_rule {
      name                = "http"
      concurrent_requests = "20"
    }
  }

  depends_on = [
    azurerm_role_assignment.app_acr_pull,
    azurerm_role_assignment.app_kv_secrets,
    azurerm_private_endpoint.keyvault,
  ]
}

# Job manual: crea el esquema pgvector e indexa el corpus versionado en la imagen.
# Ejecutar con: az containerapp job start -n <job> -g <grupo>
resource "azurerm_container_app_job" "ingest" {
  name                         = "caj-${local.name}-ingest"
  location                     = azurerm_resource_group.main.location
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  workload_profile_name        = "Consumption"
  replica_timeout_in_seconds   = 1800
  replica_retry_limit          = 0
  tags                         = local.tags

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "pg-dsn"
    key_vault_secret_id = azurerm_key_vault_secret.pg_dsn.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  template {
    container {
      name    = "ingest"
      image   = local.image
      cpu     = 1
      memory  = "2Gi"
      command = ["sh", "-c", "python -m riskrag.cli init-db && python -m riskrag.cli ingest ${var.ingest_folder}"]

      dynamic "env" {
        for_each = local.app_env
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name        = "RISKRAG_PG_DSN"
        secret_name = "pg-dsn"
      }
    }
  }

  depends_on = [
    azurerm_role_assignment.app_acr_pull,
    azurerm_role_assignment.app_kv_secrets,
    azurerm_private_endpoint.keyvault,
    azurerm_postgresql_flexible_server_configuration.extensions,
  ]
}
