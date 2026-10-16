variable "name" {
  description = "Name of the Cognitive Services account."
  type        = string
}

variable "location" {
  description = "Azure region for the account."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group that hosts the account."
  type        = string
}

variable "kind" {
  description = "Cognitive Services kind, e.g. AIServices, FormRecognizer, or TextAnalytics."
  type        = string

  validation {
    condition     = contains(["AIServices", "FormRecognizer", "ComputerVision", "TextAnalytics"], var.kind)
    error_message = "kind must be one of: AIServices, FormRecognizer, ComputerVision, TextAnalytics."
  }
}

variable "sku_name" {
  description = "SKU for the account (F0 free tier, S0/S standard)."
  type        = string
  default     = "S0"
}

variable "custom_subdomain_name" {
  description = "Globally unique custom subdomain used by the data-plane endpoint."
  type        = string
}

# Turning this on is what makes an AIServices account a "Foundry resource":
# it becomes visible in the Foundry portal and can parent accounts/projects.
variable "project_management_enabled" {
  description = "Whether the account can host Foundry projects as child resources."
  type        = bool
  default     = false
}

variable "public_network_access_enabled" {
  description = "Whether the account is reachable from the public internet."
  type        = bool
  default     = true
}

variable "local_auth_enabled" {
  description = "Whether API key authentication is permitted. Disable to force Entra ID auth."
  type        = bool
  default     = true
}

variable "outbound_network_access_restricted" {
  description = "Restrict outbound network access from the account."
  type        = bool
  default     = false
}

variable "network_acls" {
  description = "Optional network ACL rules for the account."
  type = object({
    default_action = string
    ip_rules       = optional(list(string), [])
  })
  default = null
}

variable "role_assignments" {
  description = "Role assignments scoped to this account, keyed by an arbitrary stable name."
  type = map(object({
    role_definition_name = string
    principal_id         = string
    principal_type       = optional(string, "User")
  }))
  default = {}
}

variable "tags" {
  description = "Tags applied to the account."
  type        = map(string)
  default     = {}
}
