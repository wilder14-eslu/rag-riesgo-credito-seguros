variable "subscription_id" {
  description = "Suscripción de Azure donde se despliega (az account show --query id -o tsv)"
  type        = string
}

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

variable "location" {
  description = "Región de Azure (confirmar que tenga los modelos de Azure OpenAI y Content Safety)"
  type        = string
  default     = "eastus2"
}

variable "vnet_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "container_image_tag" {
  description = "Tag inmutable de la imagen en ACR (por ejemplo el SHA del commit)"
  type        = string
}

variable "alert_email" {
  description = "Correo para alertas y presupuesto"
  type        = string
}

variable "monthly_budget_usd" {
  description = "Presupuesto mensual del grupo de recursos con alerta al 80% (pronóstico) y 100%"
  type        = number
  default     = 100
}

variable "budget_start_date" {
  description = "Primer día del mes en que empieza el presupuesto (mes actual o futuro), formato RFC 3339"
  type        = string
  default     = "2026-11-01T00:00:00Z"
  validation {
    condition     = can(regex("^\\d{4}-\\d{2}-01T00:00:00Z$", var.budget_start_date))
    error_message = "Debe ser el primer día de un mes, por ejemplo 2026-11-01T00:00:00Z."
  }
}

variable "operator_ip_cidrs" {
  description = "IP públicas (CIDR) desde donde se ejecuta Terraform; son las únicas que llegan a Key Vault"
  type        = list(string)
}

variable "api_keys_sha256" {
  description = "Hashes SHA-256 de las API keys de clientes (make api-key). Se guardan en Key Vault"
  type        = list(string)
  default     = []
  sensitive   = true
}

# Azure OpenAI: confirmar disponibilidad y fecha de retiro del modelo en la región
variable "chat_model" {
  type = object({ name = string, version = string, capacity = number })
  default = {
    name     = "gpt-4.1-mini"
    version  = "2025-04-14"
    capacity = 50 # miles de tokens por minuto
  }
}

variable "embedding_model" {
  type = object({ name = string, version = string, capacity = number })
  default = {
    name     = "text-embedding-3-large"
    version  = "1"
    capacity = 50
  }
}

variable "openai_deployment_sku" {
  description = "GlobalStandard es el más barato; DataZoneStandard o Standard mantienen los datos en la zona o región"
  type        = string
  default     = "GlobalStandard"
}

variable "postgres_sku" {
  description = "B_Standard_B1ms es suficiente para el portafolio; usar GP_Standard_D2ds_v5 en prod"
  type        = string
  default     = "B_Standard_B1ms"
}

variable "front_door_sku" {
  description = "Standard_AzureFrontDoor (reglas propias y límite de tasa) o Premium_AzureFrontDoor (agrega reglas administradas de OWASP y bots)"
  type        = string
  default     = "Standard_AzureFrontDoor"
  validation {
    condition     = contains(["Standard_AzureFrontDoor", "Premium_AzureFrontDoor"], var.front_door_sku)
    error_message = "front_door_sku debe ser Standard_AzureFrontDoor o Premium_AzureFrontDoor."
  }
}

variable "waf_rate_limit_per_5min" {
  description = "Solicitudes máximas por IP cada 5 minutos en el WAF"
  type        = number
  default     = 300
}

variable "max_replicas" {
  type    = number
  default = 2
}

variable "ingest_folder" {
  description = "Carpeta dentro de la imagen que indexa el job de ingesta"
  type        = string
  default     = "data/sample"
}
