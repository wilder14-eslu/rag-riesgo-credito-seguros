variable "project" {
  description = "Nombre corto del proyecto"
  type        = string
  default     = "riskrag"
}

variable "environment" {
  description = "Entorno: dev o prod"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment debe ser dev o prod."
  }
}

variable "region" {
  description = "Región de AWS (confirmar que los modelos de Bedrock estén habilitados aquí)"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "container_image_tag" {
  description = "Tag inmutable de la imagen en ECR (por ejemplo el SHA del commit)"
  type        = string
}

variable "acm_certificate_arn" {
  description = "Certificado ACM para el listener HTTPS del ALB"
  type        = string
}

variable "cognito_domain_prefix" {
  description = "Prefijo único del dominio de Cognito"
  type        = string
}

variable "alert_email" {
  description = "Correo para alarmas y presupuesto"
  type        = string
}

variable "monthly_budget_usd" {
  description = "Presupuesto mensual con alerta al 80% y 100%"
  type        = number
  default     = 50
}

variable "llm_model_id" {
  type    = string
  default = "anthropic.claude-3-5-sonnet-20240620-v1:0"
}

variable "embed_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

variable "rerank_model_id" {
  type    = string
  default = "cohere.rerank-v3-5:0"
}

variable "aurora_min_acu" {
  type    = number
  default = 0.5
}

variable "aurora_max_acu" {
  type    = number
  default = 2
}

variable "enable_interface_endpoints" {
  description = "Endpoints privados. Tienen costo por hora. Sin ellos y sin NAT, las tareas no pueden leer ECR ni Secrets Manager: desactivar solo si se agrega un NAT."
  type        = bool
  default     = true
}

variable "waf_rate_limit_per_5min" {
  type    = number
  default = 300
}

variable "app_domain" {
  description = "Dominio público de la app (el del certificado ACM), por ejemplo riskrag.midominio.com"
  type        = string
}

variable "extra_bedrock_resource_arns" {
  description = "ARN adicionales que la tarea puede invocar, por ejemplo perfiles de inferencia de modelos Claude recientes (inference-profile/us.anthropic...) y los foundation-model de las regiones a las que enrutan"
  type        = list(string)
  default     = []
}

variable "trust_alb_oidc" {
  description = "La API acepta la identidad firmada por el ALB (usuarios de Cognito) además de API keys"
  type        = bool
  default     = true
}
