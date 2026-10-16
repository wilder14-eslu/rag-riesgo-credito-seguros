# Key Vault con RBAC: la API lee los secretos con su identidad administrada.
# El acceso público solo se permite desde las IP del operador (para que Terraform escriba
# los secretos); Container Apps entra por el endpoint privado.

resource "azurerm_key_vault" "main" {
  #checkov:skip=CKV_AZURE_189:Acceso público limitado a las IP del operador (network_acls Deny); las apps usan el endpoint privado
  name                          = "kv-${local.name_alt}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = true
  soft_delete_retention_days    = 7
  public_network_access_enabled = true
  tags                          = local.tags

  network_acls {
    default_action = "Deny"
    bypass         = "AzureServices"
    ip_rules       = var.operator_ip_cidrs
  }
}

resource "azurerm_private_endpoint" "keyvault" {
  name                = "pe-${local.name}-keyvault"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.endpoints.id
  tags                = local.tags

  private_service_connection {
    name                           = "keyvault"
    private_connection_resource_id = azurerm_key_vault.main.id
    subresource_names              = ["vault"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "keyvault"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["keyvault"].id]
  }
}

resource "azurerm_key_vault_secret" "pg_dsn" {
  name         = "pg-dsn"
  key_vault_id = azurerm_key_vault.main.id
  content_type = "libpq-dsn"
  value = join(" ", [
    "host=${azurerm_postgresql_flexible_server.main.fqdn}",
    "port=5432",
    "user=${azurerm_postgresql_flexible_server.main.administrator_login}",
    "password=${random_password.postgres.result}",
    "dbname=${azurerm_postgresql_flexible_server_database.riskrag.name}",
    "sslmode=require",
  ])
  expiration_date = timeadd(plantimestamp(), "8760h") # rotar al menos una vez al año

  depends_on = [azurerm_role_assignment.operator_kv]

  lifecycle {
    ignore_changes = [expiration_date]
  }
}

resource "azurerm_key_vault_secret" "api_keys" {
  name            = "api-keys-sha256"
  key_vault_id    = azurerm_key_vault.main.id
  content_type    = "application/json"
  value           = jsonencode(var.api_keys_sha256)
  expiration_date = timeadd(plantimestamp(), "8760h")

  depends_on = [azurerm_role_assignment.operator_kv]

  lifecycle {
    ignore_changes = [expiration_date]
  }
}
