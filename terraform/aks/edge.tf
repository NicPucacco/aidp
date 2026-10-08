# The platform's edge (ADR-0017): a static public IP for the Gateway, the DNS
# zone with a wildcard record pointing at it, and cert-manager's identity for
# DNS-01. Owned here, not by the cluster, so DNS is correct before the cluster
# exists and survives the cluster being rebuilt.

locals {
  role_dns_zone_contributor = "${local.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/befefa01-2a29-4197-83a8-272ff33ce314"
}

resource "azapi_resource" "gateway_ip" {
  type      = "Microsoft.Network/publicIPAddresses@2024-05-01"
  name      = "pip-gateway-${local.suffix}"
  location  = var.location
  parent_id = azapi_resource.resource_group.id
  tags      = local.tags
  body = {
    sku   = { name = "Standard", tier = "Regional" }
    zones = ["1", "2", "3"]
    properties = {
      publicIPAllocationMethod = "Static"
      publicIPAddressVersion   = "IPv4"
    }
  }
  response_export_values = ["properties.ipAddress"]
}

# The cluster's identity attaches the IP to the load balancer it manages.
resource "random_uuid" "gateway_ip_network_contributor" {}

resource "azapi_resource" "gateway_ip_network_contributor" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = random_uuid.gateway_ip_network_contributor.result
  parent_id = azapi_resource.gateway_ip.id
  body = {
    properties = {
      principalId      = azapi_resource.cluster_identity.output.properties.principalId
      principalType    = "ServicePrincipal"
      roleDefinitionId = local.network_contributor
    }
  }
  retry = {
    error_message_regex  = ["PrincipalNotFound", "does not exist in the directory"]
    interval_seconds     = 10
    max_interval_seconds = 60
  }
}

resource "azapi_resource" "dns_zone" {
  type                   = "Microsoft.Network/dnsZones@2018-05-01"
  name                   = var.base_domain
  location               = "global"
  parent_id              = azapi_resource.resource_group.id
  tags                   = local.tags
  body                   = { properties = { zoneType = "Public" } }
  response_export_values = ["properties.nameServers"]
}

# Alias record: follows the IP resource, so it can't drift from the address.
resource "azapi_resource" "wildcard_record" {
  type      = "Microsoft.Network/dnsZones/A@2018-05-01"
  name      = "*"
  parent_id = azapi_resource.dns_zone.id
  body = {
    properties = {
      TTL            = 300
      targetResource = { id = azapi_resource.gateway_ip.id }
    }
  }
}

# cert-manager: DNS Zone Contributor on this zone only, via workload identity.
resource "azapi_resource" "cert_manager_identity" {
  type                   = "Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31"
  name                   = "id-cert-manager-${local.suffix}"
  location               = var.location
  parent_id              = azapi_resource.resource_group.id
  tags                   = local.tags
  response_export_values = ["properties.principalId", "properties.clientId"]
}

resource "random_uuid" "cert_manager_dns" {}

resource "azapi_resource" "cert_manager_dns" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = random_uuid.cert_manager_dns.result
  parent_id = azapi_resource.dns_zone.id
  body = {
    properties = {
      principalId      = azapi_resource.cert_manager_identity.output.properties.principalId
      principalType    = "ServicePrincipal"
      roleDefinitionId = local.role_dns_zone_contributor
    }
  }
  retry = {
    error_message_regex  = ["PrincipalNotFound", "does not exist in the directory"]
    interval_seconds     = 10
    max_interval_seconds = 60
  }
}

# Trust tokens for system:serviceaccount:cert-manager:cert-manager issued by
# this cluster's OIDC issuer, and nothing else.
resource "azapi_resource" "cert_manager_federation" {
  type      = "Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31"
  name      = "cert-manager"
  parent_id = azapi_resource.cert_manager_identity.id
  body = {
    properties = {
      issuer    = module.aks.oidc_issuer_profile_issuer_url
      subject   = "system:serviceaccount:cert-manager:cert-manager"
      audiences = ["api://AzureADTokenExchange"]
    }
  }
}
