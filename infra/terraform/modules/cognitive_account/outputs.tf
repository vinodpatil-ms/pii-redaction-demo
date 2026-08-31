output "id" {
  description = "Resource ID of the Cognitive Services account."
  value       = azurerm_cognitive_account.this.id
}

output "name" {
  description = "Name of the Cognitive Services account."
  value       = azurerm_cognitive_account.this.name
}

output "endpoint" {
  description = "Data-plane endpoint of the account."
  value       = azurerm_cognitive_account.this.endpoint
}

output "principal_id" {
  description = "Object ID of the system-assigned managed identity."
  value       = azurerm_cognitive_account.this.identity[0].principal_id
}

# No API key output by design: an output writes the key to state in plaintext.
# Callers authenticate with Entra ID tokens.
