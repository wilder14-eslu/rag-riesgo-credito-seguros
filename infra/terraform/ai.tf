# Azure OpenAI y Azure AI Content Safety: sin claves (solo Entra ID) y sin acceso público.

resource "azurerm_cognitive_account" "openai" {
  #checkov:skip=CKV_AZURE_247:La salida está restringida y la lista de FQDN permitidos queda vacía a propósito
  #checkov:skip=CKV2_AZURE_22:Cifrado con claves administradas por Microsoft; CMK queda para prod (ADR 0006)
  name                               = "oai-${local.name}-${random_string.suffix.result}"
  location                           = azurerm_resource_group.main.location
  resource_group_name                = azurerm_resource_group.main.name
  kind                               = "OpenAI"
  sku_name                           = "S0"
  custom_subdomain_name              = "oai-${local.name}-${random_string.suffix.result}"
  local_auth_enabled                 = false
  public_network_access_enabled      = false
  outbound_network_access_restricted = true # prevención de fuga de datos: el servicio no llama afuera
  fqdns                              = []
  tags                               = local.tags

  identity {
    type = "SystemAssigned"
  }

  network_acls {
    default_action = "Deny"
  }
}

resource "azurerm_cognitive_deployment" "chat" {
  name                 = var.chat_model.name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.chat_model.name
    version = var.chat_model.version
  }

  sku {
    name     = var.openai_deployment_sku
    capacity = var.chat_model.capacity
  }
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = var.embedding_model.name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.embedding_model.name
    version = var.embedding_model.version
  }

  sku {
    name     = var.openai_deployment_sku
    capacity = var.embedding_model.capacity
  }

  depends_on = [azurerm_cognitive_deployment.chat] # el servicio rechaza despliegues en paralelo
}

resource "azurerm_cognitive_account" "content_safety" {
  #checkov:skip=CKV2_AZURE_22:Cifrado con claves administradas por Microsoft; CMK queda para prod (ADR 0006)
  name                               = "cs-${local.name}-${random_string.suffix.result}"
  location                           = azurerm_resource_group.main.location
  resource_group_name                = azurerm_resource_group.main.name
  kind                               = "ContentSafety"
  sku_name                           = "S0"
  custom_subdomain_name              = "cs-${local.name}-${random_string.suffix.result}"
  local_auth_enabled                 = false
  public_network_access_enabled      = false
  outbound_network_access_restricted = true
  fqdns                              = []
  tags                               = local.tags

  identity {
    type = "SystemAssigned"
  }

  network_acls {
    default_action = "Deny"
  }
}

resource "azurerm_private_endpoint" "openai" {
  name                = "pe-${local.name}-openai"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.endpoints.id
  tags                = local.tags

  private_service_connection {
    name                           = "openai"
    private_connection_resource_id = azurerm_cognitive_account.openai.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "openai"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["openai"].id]
  }
}

resource "azurerm_private_endpoint" "content_safety" {
  name                = "pe-${local.name}-content-safety"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  subnet_id           = azurerm_subnet.endpoints.id
  tags                = local.tags

  private_service_connection {
    name                           = "content-safety"
    private_connection_resource_id = azurerm_cognitive_account.content_safety.id
    subresource_names              = ["account"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "cognitive"
    private_dns_zone_ids = [azurerm_private_dns_zone.zones["cognitive"].id]
  }
}
