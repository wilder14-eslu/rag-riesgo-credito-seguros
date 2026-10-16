terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.40"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Estado remoto recomendado (crear la cuenta de almacenamiento antes, fuera de este módulo):
  # backend "azurerm" {
  #   resource_group_name  = "riskrag-tfstate"
  #   storage_account_name = "riskragtfstate<sufijo>"
  #   container_name       = "tfstate"
  #   key                  = "riskrag-dev.tfstate"
  #   use_azuread_auth     = true
  # }
}

provider "azurerm" {
  subscription_id     = var.subscription_id
  storage_use_azuread = true

  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
    resource_group {
      prevent_deletion_if_contains_resources = true
    }
  }
}

provider "azuread" {}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

locals {
  name     = "${var.project}-${var.environment}"
  name_alt = "${var.project}${var.environment}${random_string.suffix.result}" # recursos sin guiones
  tags = {
    Proyecto    = var.project
    Entorno     = var.environment
    Responsable = "Wilder Espinoza Luna"
    Gestionado  = "terraform"
  }
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags
}
