output "api_url" {
  description = "URL pública de la API (Front Door)"
  value       = "https://${azurerm_cdn_frontdoor_endpoint.api.host_name}"
}

output "resource_group" {
  value = azurerm_resource_group.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "ingest_job_name" {
  value = azurerm_container_app_job.ingest.name
}

output "openai_endpoint" {
  value = azurerm_cognitive_account.openai.endpoint
}

output "entra_api_client_id" {
  description = "Audiencia de los tokens: los clientes piden el scope <client_id>/.default"
  value       = azuread_application.api.client_id
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.workspace_id
}
