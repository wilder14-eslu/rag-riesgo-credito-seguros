resource "aws_cognito_user_pool" "main" {
  name                     = local.name
  mfa_configuration        = "OPTIONAL"
  deletion_protection      = var.environment == "prod" ? "ACTIVE" : "INACTIVE"
  auto_verified_attributes = ["email"]
  username_attributes      = ["email"]

  admin_create_user_config { allow_admin_create_user_only = true }

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 3
  }

  software_token_mfa_configuration { enabled = true }

  # La protección avanzada contra amenazas requiere el plan PLUS de Cognito (con costo).
  # Para activarla: proveedor >= 5.83, user_pool_tier = "PLUS" y el bloque user_pool_add_ons.
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = var.cognito_domain_prefix
  user_pool_id = aws_cognito_user_pool.main.id
}

resource "aws_cognito_user_pool_client" "alb" {
  name                                 = "${local.name}-alb"
  user_pool_id                         = aws_cognito_user_pool.main.id
  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = ["https://${var.app_domain}/oauth2/idpresponse"]
  prevent_user_existence_errors        = "ENABLED"
}
