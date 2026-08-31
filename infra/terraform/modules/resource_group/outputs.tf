output "name" {
  description = "Name of the resource group."
  value       = azurerm_resource_group.this.name
}

output "location" {
  description = "Region of the resource group."
  value       = azurerm_resource_group.this.location
}

output "id" {
  description = "Resource ID of the resource group."
  value       = azurerm_resource_group.this.id
}
