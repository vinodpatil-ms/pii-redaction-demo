# Custom subdomains must be globally unique, so suffix them deterministically per RG.
resource "random_string" "suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false

  keepers = {
    resource_group_name = var.resource_group_name
  }
}

data "azurerm_client_config" "current" {}

locals {
  data_plane_principal_ids = length(var.data_plane_principal_ids) > 0 ? var.data_plane_principal_ids : [data.azurerm_client_config.current.object_id]

  # Keys are stable per principal so adding the portal role doesn't recreate the existing assignment.
  data_plane_role_assignments = merge(
    {
      for id in local.data_plane_principal_ids : id => {
        role_definition_name = "Cognitive Services User"
        principal_id         = id
        principal_type       = var.data_plane_principal_type
      }
    },
    {
      # Grants access to the resource and its projects in the Foundry portal.
      for id in local.data_plane_principal_ids : "${id}-foundry-user" => {
        role_definition_name = "Foundry User"
        principal_id         = id
        principal_type       = var.data_plane_principal_type
      }
    }
  )
}

module "resource_group" {
  source = "../../modules/resource_group"

  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

# Language PII account; project_management_enabled makes it a Foundry resource.
module "ai_services" {
  source = "../../modules/cognitive_account"

  name                       = "cog-${var.name_prefix}-aiservices-${random_string.suffix.result}"
  location                   = module.resource_group.location
  resource_group_name        = module.resource_group.name
  kind                       = "AIServices"
  sku_name                   = var.ai_services_sku_name
  custom_subdomain_name      = "cog-${var.name_prefix}-aiservices-${random_string.suffix.result}"
  local_auth_enabled         = var.local_auth_enabled
  project_management_enabled = true
  role_assignments           = local.data_plane_role_assignments
  tags                       = merge(var.tags, { service = "ai-services" })
}

module "document_intelligence" {
  source = "../../modules/cognitive_account"

  name                  = "cog-${var.name_prefix}-docintel-${random_string.suffix.result}"
  location              = module.resource_group.location
  resource_group_name   = module.resource_group.name
  kind                  = "FormRecognizer"
  sku_name              = var.document_intelligence_sku_name
  custom_subdomain_name = "cog-${var.name_prefix}-docintel-${random_string.suffix.result}"
  local_auth_enabled    = var.local_auth_enabled
  role_assignments = {
    for id in local.data_plane_principal_ids : id => {
      role_definition_name = "Cognitive Services User"
      principal_id         = id
      principal_type       = var.data_plane_principal_type
    }
  }
  tags = merge(var.tags, { service = "document-intelligence" })
}

# Development boundary for playgrounds, evaluations, and traces. Data-plane calls
# use the Language and Document Intelligence account endpoints, not the project.
resource "azurerm_cognitive_account_project" "default" {
  name                 = var.project_name
  cognitive_account_id = module.ai_services.id
  location             = module.resource_group.location
  display_name         = var.project_name
  description          = "PII detection and redaction demo"

  identity {
    type = "SystemAssigned"
  }

  tags = var.tags
}
