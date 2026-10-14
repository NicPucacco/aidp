# What the Database API needs on Azure (ADR-0019): a resource group for the
# servers, private networking, and the identity Crossplane's Azure provider
# runs as. The servers themselves are created by Crossplane per Database, not
# here.

locals {
  role_contributor               = "${local.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/b24988ac-6180-42a0-ab88-20f7382dd24c"
  role_private_dns_zone_contrib  = "${local.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/b12aa53e-6015-4669-85d0-8515ebb3ae7f"
  postgres_provider_subject      = "system:serviceaccount:crossplane-system:provider-azure-dbforpostgresql"
  postgres_private_dns_zone_name = "${local.suffix}.private.postgres.database.azure.com"
}

# Servers live apart from the cluster, so the provider's identity can be
# Contributor here without any rights over the cluster's own resources.
resource "azapi_resource" "data_resource_group" {
  type      = "Microsoft.Resources/resourceGroups@2024-03-01"
  name      = "rg-${local.suffix}-data"
  location  = var.location
  parent_id = local.subscription_id
  tags      = local.tags
}

# Private access only: servers get an address in this delegated subnet and
# are reachable from the cluster, not the internet.
resource "azapi_resource" "subnet_postgres" {
  type      = "Microsoft.Network/virtualNetworks/subnets@2024-05-01"
  name      = "snet-postgres"
  parent_id = azapi_resource.vnet.id
  body = {
    properties = {
      addressPrefix = cidrsubnet(var.vnet_address_space, 8, 2) # /24
      delegations = [{
        name       = "postgres-flexible-server"
        properties = { serviceName = "Microsoft.DBforPostgreSQL/flexibleServers" }
      }]
    }
  }

  # Writes to one VNet's subnets must be serial.
  depends_on = [azapi_resource.subnet_nodes]
}

# Flexible Server private access requires a zone ending in
# .postgres.database.azure.com, linked to the VNet the clients are in.
resource "azapi_resource" "postgres_private_dns_zone" {
  type      = "Microsoft.Network/privateDnsZones@2024-06-01"
  name      = local.postgres_private_dns_zone_name
  location  = "global"
  parent_id = azapi_resource.resource_group.id
  tags      = local.tags
}

resource "azapi_resource" "postgres_private_dns_link" {
  type      = "Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01"
  name      = "vnet-${local.suffix}"
  location  = "global"
  parent_id = azapi_resource.postgres_private_dns_zone.id
  body = {
    properties = {
      registrationEnabled = false
      virtualNetwork      = { id = azapi_resource.vnet.id }
    }
  }
}

# The identity Crossplane's Azure provider runs as (workload identity).
resource "azapi_resource" "crossplane_azure_identity" {
  type                   = "Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31"
  name                   = "id-crossplane-azure-${local.suffix}"
  location               = var.location
  parent_id              = azapi_resource.resource_group.id
  tags                   = local.tags
  response_export_values = ["properties.principalId", "properties.clientId"]
}

locals {
  crossplane_azure_roles = {
    data_rg  = { scope = azapi_resource.data_resource_group.id, role = local.role_contributor }
    subnet   = { scope = azapi_resource.subnet_postgres.id, role = local.network_contributor }
    dns_zone = { scope = azapi_resource.postgres_private_dns_zone.id, role = local.role_private_dns_zone_contrib }
  }
}

resource "random_uuid" "crossplane_azure_role" {
  for_each = local.crossplane_azure_roles
}

resource "azapi_resource" "crossplane_azure_role" {
  for_each = local.crossplane_azure_roles

  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = random_uuid.crossplane_azure_role[each.key].result
  parent_id = each.value.scope
  body = {
    properties = {
      principalId      = azapi_resource.crossplane_azure_identity.output.properties.principalId
      principalType    = "ServicePrincipal"
      roleDefinitionId = each.value.role
    }
  }
  retry = {
    error_message_regex  = ["PrincipalNotFound", "does not exist in the directory"]
    interval_seconds     = 10
    max_interval_seconds = 60
  }
}

resource "azapi_resource" "crossplane_azure_federation" {
  type      = "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31"
  name      = "crossplane-provider-azure-dbforpostgresql"
  parent_id = azapi_resource.crossplane_azure_identity.id
  body = {
    properties = {
      issuer    = module.aks.oidc_issuer_profile_issuer_url
      subject   = local.postgres_provider_subject
      audiences = ["api://AzureADTokenExchange"]
    }
  }
}
