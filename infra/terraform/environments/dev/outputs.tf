output "resource_group_name" {
  description = "Name of the deployed resource group."
  value       = module.resource_group.name
}

output "ai_services_endpoint" {
  description = "Shared endpoint for the Azure AI Services account (Vision OCR and Language PII)."
  value       = module.ai_services.endpoint
}

output "ai_services_name" {
  description = "Name of the Azure AI Services account."
  value       = module.ai_services.name
}

# Scope for granting callers the "Cognitive Services User" role.
output "ai_services_id" {
  description = "Resource ID of the Azure AI Services account."
  value       = module.ai_services.id
}

output "ai_project_name" {
  description = "Name of the Foundry project."
  value       = azurerm_cognitive_account_project.default.name
}

# Only the Foundry/agent APIs are project-scoped; Language and Vision stay on the account endpoint.
output "ai_project_endpoint" {
  description = "Project-scoped Foundry API endpoint."
  value       = lookup(azurerm_cognitive_account_project.default.endpoints, "AI Foundry API", null)
}
