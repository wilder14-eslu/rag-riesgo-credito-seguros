# Log Analytics recibe la consola de Container Apps (incluida la auditoría JSON),
# los registros de diagnóstico de cada servicio y alimenta las alertas.

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 90
  daily_quota_gb      = 1 # techo de costo
  tags                = local.tags
}

locals {
  diagnostics = {
    keyvault       = azurerm_key_vault.main.id
    postgres       = azurerm_postgresql_flexible_server.main.id
    openai         = azurerm_cognitive_account.openai.id
    content_safety = azurerm_cognitive_account.content_safety.id
    frontdoor      = azurerm_cdn_frontdoor_profile.main.id
  }
}

resource "azurerm_monitor_diagnostic_setting" "services" {
  for_each                   = local.diagnostics
  name                       = "diag-${each.key}"
  target_resource_id         = each.value
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category_group = each.key == "frontdoor" ? "allLogs" : "audit"
  }
}

resource "azurerm_monitor_action_group" "alerts" {
  name                = "ag-${local.name}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "riskrag"
  tags                = local.tags

  email_receiver {
    name                    = "operador"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }
}

resource "azurerm_monitor_metric_alert" "api_5xx" {
  name                = "${local.name}-5xx"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_container_app.api.id]
  description         = "Errores 5xx de la API"
  frequency           = "PT5M"
  window_size         = "PT5M"
  severity            = 2
  tags                = local.tags

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "Requests"
    aggregation      = "Total"
    operator         = "GreaterThanOrEqual"
    threshold        = 5

    dimension {
      name     = "statusCodeCategory"
      operator = "Include"
      values   = ["5xx"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.alerts.id
  }
}

# Pico de consultas bloqueadas por seguridad, leído del log de auditoría
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "blocked_spike" {
  name                 = "${local.name}-pico-bloqueos"
  resource_group_name  = azurerm_resource_group.main.name
  location             = azurerm_resource_group.main.location
  scopes               = [azurerm_log_analytics_workspace.main.id]
  description          = "Muchas consultas bloqueadas por los guardrails en 5 minutos"
  severity             = 2
  evaluation_frequency = "PT5M"
  window_duration      = "PT5M"
  tags                 = local.tags

  criteria {
    query                   = <<-KQL
      ContainerAppConsoleLogs_CL
      | where ContainerAppName_s == "${azurerm_container_app.api.name}"
      | where Log_s has "query_blocked"
    KQL
    time_aggregation_method = "Count"
    operator                = "GreaterThanOrEqual"
    threshold               = 20
  }

  action {
    action_groups = [azurerm_monitor_action_group.alerts.id]
  }
}

resource "azurerm_consumption_budget_resource_group" "monthly" {
  name              = "budget-${local.name}"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.monthly_budget_usd
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }

  lifecycle {
    ignore_changes = [time_period]
  }
}
