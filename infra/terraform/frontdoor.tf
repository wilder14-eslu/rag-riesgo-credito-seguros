# Azure Front Door con WAF delante de la API: HTTPS con certificado administrado,
# límite de tasa por IP y, en Premium, reglas administradas de OWASP y bots.

resource "azurerm_cdn_frontdoor_profile" "main" {
  name                = "afd-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = var.front_door_sku
  tags                = local.tags
}

resource "azurerm_cdn_frontdoor_endpoint" "api" {
  name                     = "${local.name}-${random_string.suffix.result}"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id
  tags                     = local.tags
}

resource "azurerm_cdn_frontdoor_origin_group" "api" {
  name                     = "api"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id
  session_affinity_enabled = false

  load_balancing {
    sample_size                 = 4
    successful_samples_required = 3
  }

  # Sin sondas de salud: con un solo origen no aportan y sus solicitudes desde cada
  # punto de presencia impedirían que Container Apps escale a cero (costo).
}

resource "azurerm_cdn_frontdoor_origin" "api" {
  name                           = "container-app"
  cdn_frontdoor_origin_group_id  = azurerm_cdn_frontdoor_origin_group.api.id
  enabled                        = true
  host_name                      = azurerm_container_app.api.ingress[0].fqdn
  origin_host_header             = azurerm_container_app.api.ingress[0].fqdn
  http_port                      = 80
  https_port                     = 443
  priority                       = 1
  weight                         = 1000
  certificate_name_check_enabled = true
}

resource "azurerm_cdn_frontdoor_route" "api" {
  name                          = "api"
  cdn_frontdoor_endpoint_id     = azurerm_cdn_frontdoor_endpoint.api.id
  cdn_frontdoor_origin_group_id = azurerm_cdn_frontdoor_origin_group.api.id
  cdn_frontdoor_origin_ids      = [azurerm_cdn_frontdoor_origin.api.id]
  supported_protocols           = ["Http", "Https"]
  https_redirect_enabled        = true
  forwarding_protocol           = "HttpsOnly"
  patterns_to_match             = ["/*"]
  link_to_default_domain        = true
}

resource "azurerm_cdn_frontdoor_firewall_policy" "main" {
  name                = "waf${replace(local.name, "-", "")}"
  resource_group_name = azurerm_resource_group.main.name
  sku_name            = var.front_door_sku
  enabled             = true
  mode                = "Prevention"
  tags                = local.tags

  custom_rule {
    name                           = "LimitePorIP"
    priority                       = 100
    type                           = "RateLimitRule"
    action                         = "Block"
    rate_limit_duration_in_minutes = 5
    rate_limit_threshold           = var.waf_rate_limit_per_5min

    match_condition {
      match_variable = "RequestUri"
      operator       = "BeginsWith"
      match_values   = ["/"]
    }
  }

  # Cuerpo máximo: las preguntas son cortas, un cuerpo grande es abuso
  custom_rule {
    name     = "CuerpoGrande"
    priority = 200
    type     = "MatchRule"
    action   = "Block"

    match_condition {
      match_variable = "RequestHeader"
      selector       = "Content-Length"
      operator       = "GreaterThan"
      match_values   = ["16384"]
    }
  }

  dynamic "managed_rule" {
    for_each = var.front_door_sku == "Premium_AzureFrontDoor" ? [1] : []
    content {
      type    = "Microsoft_DefaultRuleSet"
      version = "2.1"
      action  = "Block"
    }
  }

  dynamic "managed_rule" {
    for_each = var.front_door_sku == "Premium_AzureFrontDoor" ? [1] : []
    content {
      type    = "Microsoft_BotManagerRuleSet"
      version = "1.1"
      action  = "Block"
    }
  }
}

resource "azurerm_cdn_frontdoor_security_policy" "main" {
  name                     = "waf"
  cdn_frontdoor_profile_id = azurerm_cdn_frontdoor_profile.main.id

  security_policies {
    firewall {
      cdn_frontdoor_firewall_policy_id = azurerm_cdn_frontdoor_firewall_policy.main.id

      association {
        patterns_to_match = ["/*"]

        domain {
          cdn_frontdoor_domain_id = azurerm_cdn_frontdoor_endpoint.api.id
        }
      }
    }
  }
}
