# Aurora PostgreSQL Serverless v2 con pgvector. La contraseña maestra la gestiona
# RDS en Secrets Manager (nunca pasa por Terraform ni por el repositorio).

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_rds_cluster" "main" {
  cluster_identifier                  = local.name
  engine                              = "aurora-postgresql"
  engine_mode                         = "provisioned"
  engine_version                      = "16.4"
  database_name                       = "riskrag"
  master_username                     = "riskrag_admin"
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = aws_kms_key.main.key_id
  db_subnet_group_name                = aws_db_subnet_group.main.name
  vpc_security_group_ids              = [aws_security_group.db.id]
  storage_encrypted                   = true
  kms_key_id                          = aws_kms_key.main.arn
  iam_database_authentication_enabled = true
  backup_retention_period             = var.environment == "prod" ? 14 : 3
  deletion_protection                 = var.environment == "prod"
  skip_final_snapshot                 = var.environment != "prod"
  final_snapshot_identifier           = var.environment == "prod" ? "${local.name}-final" : null
  enabled_cloudwatch_logs_exports     = ["postgresql"]
  copy_tags_to_snapshot               = true

  serverlessv2_scaling_configuration {
    min_capacity = var.aurora_min_acu
    max_capacity = var.aurora_max_acu
  }

  # Las actualizaciones menores automáticas cambian la versión; no intentar revertirlas
  lifecycle {
    ignore_changes = [engine_version]
  }
}

resource "aws_rds_cluster_instance" "main" {
  identifier                      = "${local.name}-1"
  cluster_identifier              = aws_rds_cluster.main.id
  instance_class                  = "db.serverless"
  engine                          = aws_rds_cluster.main.engine
  engine_version                  = aws_rds_cluster.main.engine_version
  publicly_accessible             = false
  performance_insights_enabled    = true
  performance_insights_kms_key_id = aws_kms_key.main.arn

  lifecycle {
    ignore_changes = [engine_version]
  }
}
