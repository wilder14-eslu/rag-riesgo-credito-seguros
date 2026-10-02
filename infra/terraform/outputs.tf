output "alb_dns_name" {
  description = "Apuntar el registro DNS de app_domain a este nombre"
  value       = aws_lb.main.dns_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.api.repository_url
}

output "corpus_bucket" {
  value = aws_s3_bucket.corpus.bucket
}

output "aurora_endpoint" {
  value = aws_rds_cluster.main.endpoint
}

output "guardrail_id" {
  value = aws_bedrock_guardrail.main.guardrail_id
}

output "secret_api_keys_arn" {
  value = aws_secretsmanager_secret.api_keys.arn
}

output "secret_pg_dsn_arn" {
  value = aws_secretsmanager_secret.pg_dsn.arn
}
