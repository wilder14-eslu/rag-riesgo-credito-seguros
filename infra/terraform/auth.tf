# Registro de la API en Microsoft Entra ID. Los clientes piden un token con el rol
# RiskRAG.Query (flujo client credentials para apps o asignación a usuarios) y la API
# verifica firma, emisor, audiencia y rol (src/riskrag/api/security.py).

resource "random_uuid" "role_query" {}

resource "azuread_application" "api" {
  display_name     = "${local.name}-api"
  sign_in_audience = "AzureADMyOrg"

  api {
    requested_access_token_version = 2
  }

  app_role {
    allowed_member_types = ["Application", "User"]
    description          = "Consultar el asistente RiskRAG"
    display_name         = "RiskRAG.Query"
    enabled              = true
    id                   = random_uuid.role_query.result
    value                = "RiskRAG.Query"
  }
}

resource "azuread_service_principal" "api" {
  client_id                    = azuread_application.api.client_id
  app_role_assignment_required = true
}
