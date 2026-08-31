resource "azurerm_cognitive_account" "this" {
  name                = var.name
  location            = var.location
  resource_group_name = var.resource_group_name
  kind                = var.kind
  sku_name            = var.sku_name

  # Required for token-based (Entra ID) auth against the data plane.
  custom_subdomain_name = var.custom_subdomain_name

  project_management_enabled = var.project_management_enabled

  public_network_access_enabled      = var.public_network_access_enabled
  local_auth_enabled                 = var.local_auth_enabled
  outbound_network_access_restricted = var.outbound_network_access_restricted

  identity {
    type = "SystemAssigned"
  }

  dynamic "network_acls" {
    for_each = var.network_acls == null ? [] : [var.network_acls]

    content {
      default_action = network_acls.value.default_action
      ip_rules       = network_acls.value.ip_rules
    }
  }

  tags = var.tags
}

# Data-plane access is RBAC-only when local auth is disabled.
resource "azurerm_role_assignment" "this" {
  for_each = var.role_assignments

  scope                = azurerm_cognitive_account.this.id
  role_definition_name = each.value.role_definition_name
  principal_id         = each.value.principal_id
  principal_type       = each.value.principal_type
}
