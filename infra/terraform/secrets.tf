# Contenedores de secretos SIN valor: los valores se cargan fuera de Terraform para que
# nunca queden en el estado ni en el repositorio. Ver docs/09_despliegue_aws.md.

resource "aws_secretsmanager_secret" "api_keys" {
  name        = "${local.name}/api-keys-sha256"
  description = "Lista JSON de hashes SHA-256 de las API keys aceptadas"
  kms_key_id  = aws_kms_key.main.arn
}

resource "aws_secretsmanager_secret" "pg_dsn" {
  name        = "${local.name}/pg-dsn-app"
  description = "Cadena de conexión del usuario de aplicación (no el maestro) a Aurora"
  kms_key_id  = aws_kms_key.main.arn
}
