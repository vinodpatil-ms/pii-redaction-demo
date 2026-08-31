variable "subscription_id" {
  description = "Azure subscription ID to deploy into."
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group to create."
  type        = string
  default     = "rg-demo-pii-redaction"
}

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus"
}

variable "name_prefix" {
  description = "Prefix used when naming the Cognitive Services accounts."
  type        = string
  default     = "demo-pii"
}

variable "ai_services_sku_name" {
  description = "SKU for the multi-service Azure AI Services account."
  type        = string
  default     = "S0"
}

variable "project_name" {
  description = "Name of the Foundry project created under the AI Services account."
  type        = string
  default     = "proj-demo-pii"
}

# Defaults to false so the account is Entra ID only. Some tenants enforce
# disableLocalAuth=true via Azure Policy, which overrides this setting.
variable "local_auth_enabled" {
  description = "Whether API key authentication is permitted on the account."
  type        = bool
  default     = false
}

variable "data_plane_principal_ids" {
  description = "Entra ID object IDs granted 'Cognitive Services User'. Defaults to the deploying principal."
  type        = list(string)
  default     = []
}

variable "data_plane_principal_type" {
  description = "Principal type for the data-plane role assignments: User, Group, or ServicePrincipal."
  type        = string
  default     = "User"
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    environment = "dev"
    workload    = "pii-redaction"
    managed_by  = "terraform"
  }
}
