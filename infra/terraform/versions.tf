terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }

  # Estado remoto recomendado (crear el bucket y la tabla antes, fuera de este módulo):
  # backend "s3" {
  #   bucket         = "riskrag-tfstate-<cuenta>"
  #   key            = "riskrag/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "riskrag-tflock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Proyecto    = var.project
      Entorno     = var.environment
      Responsable = "Wilder Espinoza Luna"
      Gestionado  = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" { state = "available" }

locals {
  name       = "${var.project}-${var.environment}"
  account_id = data.aws_caller_identity.current.account_id
  azs        = slice(data.aws_availability_zones.available.names, 0, 2)
}
