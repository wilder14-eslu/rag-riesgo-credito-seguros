# ECR + ECS Fargate en subredes privadas, detrás de un ALB con HTTPS y Cognito.

resource "aws_ecr_repository" "api" {
  name                 = local.name
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.main.arn
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Conservar las ultimas 15 imagenes"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 15 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  volume { name = "tmp" }

  container_definitions = jsonencode([{
    name                   = "api"
    image                  = "${aws_ecr_repository.api.repository_url}:${var.container_image_tag}"
    essential              = true
    readonlyRootFilesystem = true
    user                   = "10001"
    portMappings           = [{ containerPort = 8000, protocol = "tcp" }]
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp" }]
    linuxParameters        = { capabilities = { drop = ["ALL"] }, initProcessEnabled = true }
    environment = [
      { name = "RISKRAG_ENV", value = var.environment == "prod" ? "prod" : "dev" },
      { name = "RISKRAG_AWS_REGION", value = var.region },
      { name = "RISKRAG_EMBEDDER_BACKEND", value = "bedrock" },
      { name = "RISKRAG_VECTOR_BACKEND", value = "pgvector" },
      { name = "RISKRAG_LLM_BACKEND", value = "bedrock" },
      { name = "RISKRAG_RERANKER_BACKEND", value = "bedrock" },
      { name = "RISKRAG_GUARDRAIL_BACKEND", value = "bedrock" },
      { name = "RISKRAG_BEDROCK_LLM_MODEL_ID", value = var.llm_model_id },
      { name = "RISKRAG_BEDROCK_EMBED_MODEL_ID", value = var.embed_model_id },
      { name = "RISKRAG_BEDROCK_RERANK_MODEL_ID", value = var.rerank_model_id },
      { name = "RISKRAG_BEDROCK_GUARDRAIL_ID", value = aws_bedrock_guardrail.main.guardrail_id },
      { name = "RISKRAG_BEDROCK_GUARDRAIL_VERSION", value = aws_bedrock_guardrail_version.main.version },
      { name = "RISKRAG_AUDIT_LOG_PATH", value = "/tmp/audit/audit.jsonl" },
      { name = "RISKRAG_AUDIT_STDOUT", value = "true" },
      { name = "RISKRAG_PROJECT_ROOT", value = "/app" },
      { name = "RISKRAG_TRUST_ALB_OIDC", value = tostring(var.trust_alb_oidc) },
      { name = "RISKRAG_ALB_ARN", value = aws_lb.main.arn },
    ]
    secrets = [
      { name = "RISKRAG_API_KEYS_SHA256", valueFrom = aws_secretsmanager_secret.api_keys.arn },
      { name = "RISKRAG_PG_DSN", valueFrom = aws_secretsmanager_secret.pg_dsn.arn },
    ]
    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')\""]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "api"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "${local.name}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.environment == "prod" ? 2 : 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.https]
}

# --- Balanceador ---
resource "aws_lb" "main" {
  name                       = local.name
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = aws_subnet.public[*].id
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  enable_deletion_protection = var.environment == "prod"
}

resource "aws_lb_target_group" "api" {
  name        = "${local.name}-api"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id
  health_check {
    path    = "/health"
    matcher = "200"
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  # Usuarios humanos (demo web): autenticación con Cognito antes de llegar a la API
  default_action {
    type  = "authenticate-cognito"
    order = 1
    authenticate_cognito {
      user_pool_arn       = aws_cognito_user_pool.main.arn
      user_pool_client_id = aws_cognito_user_pool_client.alb.id
      user_pool_domain    = aws_cognito_user_pool_domain.main.domain
    }
  }
  default_action {
    type             = "forward"
    order            = 2
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# Clientes programáticos (agentes MCP remotos, CI de evaluación): ruta /v1/* con API key
# validada dentro del servicio, sin el flujo de navegador de Cognito.
resource "aws_lb_listener_rule" "api_programmatic" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  condition {
    path_pattern { values = ["/v1/*", "/health"] }
  }
  condition {
    http_header {
      http_header_name = "x-api-key"
      values           = ["*"]
    }
  }
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
