# Azure Database for PostgreSQL Flexible Server con pgvector, solo dentro de la VNet.

resource "random_password" "postgres" {
  length           = 32
  special          = true
  override_special = "_-."
}

resource "azurerm_postgresql_flexible_server" "main" {
  #checkov:skip=CKV2_AZURE_57:Integración con VNet (subred delegada, sin acceso público) en lugar de endpoint privado
  #checkov:skip=CKV_AZURE_136:Respaldo geo-redundante desactivado por costo en dev; activar en prod
  name                          = "psql-${local.name}-${random_string.suffix.result}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  version                       = "16"
  sku_name                      = var.postgres_sku
  storage_mb                    = 32768
  backup_retention_days         = 7
  delegated_subnet_id           = azurerm_subnet.postgres.id
  private_dns_zone_id           = azurerm_private_dns_zone.zones["postgres"].id
  public_network_access_enabled = false
  administrator_login           = "riskrag_admin"
  administrator_password        = random_password.postgres.result
  zone                          = "1"
  tags                          = local.tags

  authentication {
    password_auth_enabled         = true
    active_directory_auth_enabled = false
  }

  depends_on = [azurerm_private_dns_zone_virtual_network_link.links]

  lifecycle {
    ignore_changes = [zone]
  }
}

# pgvector debe estar en la lista permitida antes de CREATE EXTENSION vector
resource "azurerm_postgresql_flexible_server_configuration" "extensions" {
  name      = "azure.extensions"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "VECTOR"
}

resource "azurerm_postgresql_flexible_server_configuration" "log_connections" {
  name      = "log_connections"
  server_id = azurerm_postgresql_flexible_server.main.id
  value     = "on"
}

resource "azurerm_postgresql_flexible_server_database" "riskrag" {
  name      = "riskrag"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}
