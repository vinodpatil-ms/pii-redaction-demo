output "resource_group_name" {
  description = "Name of the deployed resource group."
  value       = module.resource_group.name
}

output "ai_services_endpoint" {
  description = "Azure AI Services endpoint for Language PII detection."
  value       = module.ai_services.endpoint
}

output "ai_services_name" {
  description = "Name of the Azure AI Services account."
  value       = module.ai_services.name
}

output "content_understanding_endpoint" {
  description = "Foundry account endpoint for Content Understanding Read (APP_CONTENT_UNDERSTANDING_ENDPOINT), Azure public cloud."
  value       = "https://${module.content_understanding.name}.services.ai.azure.com/"
}

output "content_understanding_name" {
  description = "Name of the dedicated Content Understanding account."
  value       = module.content_understanding.name
}

output "content_understanding_id" {
  description = "Resource ID of the dedicated Content Understanding account for RBAC."
  value       = module.content_understanding.id
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

# Content Understanding and Language use account endpoints, not this project endpoint.
output "ai_project_endpoint" {
  description = "Project-scoped Foundry API endpoint."
  value       = lookup(azurerm_cognitive_account_project.default.endpoints, "AI Foundry API", null)
}

output "document_intelligence_endpoint" {
  description = "Alternative Document Intelligence Read endpoint (APP_DOCUMENT_INTELLIGENCE_ENDPOINT)."
  value       = module.document_intelligence.endpoint
}

output "document_intelligence_name" {
  description = "Name of the Document Intelligence account."
  value       = module.document_intelligence.name
}

output "document_intelligence_id" {
  description = "Resource ID of the Document Intelligence account for data-plane role assignments."
  value       = module.document_intelligence.id
}
