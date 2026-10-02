resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name}-api"
  retention_in_days = 90
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_cloudwatch_log_group" "vpc_flow" {
  name              = "/vpc/${local.name}-flow"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_sns_topic" "alerts" {
  name              = "${local.name}-alertas"
  kms_master_key_id = aws_kms_key.main.id
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${local.name}-5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Métrica a partir del log de auditoría: consultas bloqueadas por seguridad
resource "aws_cloudwatch_log_metric_filter" "blocked" {
  name           = "${local.name}-bloqueos"
  log_group_name = aws_cloudwatch_log_group.api.name
  pattern        = "{ $.event = \"query_blocked\" }"
  metric_transformation {
    name      = "ConsultasBloqueadas"
    namespace = "RiskRAG"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "blocked_spike" {
  alarm_name          = "${local.name}-pico-bloqueos"
  namespace           = "RiskRAG"
  metric_name         = "ConsultasBloqueadas"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 20
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-mensual"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}
