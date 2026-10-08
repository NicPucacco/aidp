# The AKS cluster the Fernhill platform runs on (ADR-0016).
#
# Scope: the cluster and what it needs to exist (resource group, network,
# identity, logging). Everything *on* the cluster is terraform/argocd's day-0
# bootstrap and then Argo CD (ADR-0003), so this state stays small and changes rarely.

data "azapi_client_config" "current" {}

locals {
  suffix = "${var.name_prefix}-${var.environment}"
  tags = merge(
    {
      environment = var.environment
      managed-by  = "terraform"
      repository  = "github.com/NicPucacco/aidp"
    },
    var.tags,
  )
  subscription_id = "/subscriptions/${data.azapi_client_config.current.subscription_id}"
  # Built-in role definition IDs.
  network_contributor = "${local.subscription_id}/providers/Microsoft.Authorization/roleDefinitions/4d97b98b-1d4f-4787-a291-c67834d212e7"
}

resource "azapi_resource" "resource_group" {
  type      = "Microsoft.Resources/resourceGroups@2024-03-01"
  name      = "rg-${local.suffix}"
  location  = var.location
  parent_id = local.subscription_id
  tags      = local.tags
}

# --- network -----------------------------------------------------------------

resource "azapi_resource" "vnet" {
  type      = "Microsoft.Network/virtualNetworks@2024-05-01"
  name      = "vnet-${local.suffix}"
  location  = var.location
  parent_id = azapi_resource.resource_group.id
  tags      = local.tags
  body = {
    properties = {
      addressSpace = { addressPrefixes = [var.vnet_address_space] }
    }
  }
}

# Azure CNI overlay: nodes take subnet IPs, pods get overlay IPs, so the node
# subnet only has to fit nodes, not every pod.
resource "azapi_resource" "subnet_nodes" {
  type      = "Microsoft.Network/virtualNetworks/subnets@2024-05-01"
  name      = "snet-aks-nodes"
  parent_id = azapi_resource.vnet.id
  body = {
    properties = {
      addressPrefix = cidrsubnet(var.vnet_address_space, 8, 1) # /24
    }
  }
}

# --- identity ----------------------------------------------------------------

# User-assigned so its role on the subnet exists *before* the cluster does.
resource "azapi_resource" "cluster_identity" {
  type                   = "Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31"
  name                   = "id-aks-${local.suffix}"
  location               = var.location
  parent_id              = azapi_resource.resource_group.id
  tags                   = local.tags
  response_export_values = ["properties.principalId"]
}

resource "random_uuid" "network_contributor" {}

resource "azapi_resource" "cluster_network_contributor" {
  type      = "Microsoft.Authorization/roleAssignments@2022-04-01"
  name      = random_uuid.network_contributor.result
  parent_id = azapi_resource.subnet_nodes.id
  body = {
    properties = {
      principalId      = azapi_resource.cluster_identity.output.properties.principalId
      principalType    = "ServicePrincipal"
      roleDefinitionId = local.network_contributor
    }
  }
  # A new identity can take a moment to replicate to Entra ID.
  retry = {
    error_message_regex  = ["PrincipalNotFound", "does not exist in the directory"]
    interval_seconds     = 10
    max_interval_seconds = 60
  }
}

# --- observability -----------------------------------------------------------

resource "azapi_resource" "log_analytics" {
  type      = "Microsoft.OperationalInsights/workspaces@2023-09-01"
  name      = "log-${local.suffix}"
  location  = var.location
  parent_id = azapi_resource.resource_group.id
  tags      = local.tags
  body = {
    properties = {
      retentionInDays = 30
      sku             = { name = "PerGB2018" }
    }
  }
}

# --- cluster -----------------------------------------------------------------

module "aks" {
  source  = "Azure/avm-res-containerservice-managedcluster/azurerm"
  version = "0.8.3"

  name               = "aks-${local.suffix}"
  location           = var.location
  parent_id          = azapi_resource.resource_group.id
  kubernetes_version = var.kubernetes_version
  tags               = local.tags
  enable_telemetry   = false

  # Uptime SLA on the control plane; this cluster runs production.
  sku = {
    name = "Base"
    tier = "Standard"
  }

  # Entra ID + Azure RBAC; no local accounts or static kubeconfig credentials.
  aad_profile = {
    managed                = true
    enable_azure_rbac      = true
    tenant_id              = data.azapi_client_config.current.tenant_id
    admin_group_object_ids = var.admin_group_object_ids
  }
  disable_local_accounts = true

  # Lets in-cluster components (Crossplane, External Secrets, the agent's
  # GitHub App key) authenticate to Azure without stored secrets.
  oidc_issuer_profile = { enabled = true }
  security_profile = {
    workload_identity = { enabled = true }
    image_cleaner     = { enabled = true, interval_hours = 48 }
  }

  managed_identities = {
    system_assigned            = false
    user_assigned_resource_ids = [azapi_resource.cluster_identity.id]
  }

  api_server_access_profile = {
    authorized_ip_ranges = var.api_server_authorized_ip_ranges
  }

  network_profile = {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    network_dataplane   = "cilium"
    pod_cidr            = "192.168.0.0/16"
    service_cidr        = "10.41.0.0/16"
    dns_service_ip      = "10.41.0.10"
  }

  # System pool: AKS add-ons only.
  default_agent_pool = {
    name                = "system"
    mode                = "System"
    vm_size             = var.system_pool.vm_size
    enable_auto_scaling = true
    min_count           = var.system_pool.min_count
    max_count           = var.system_pool.max_count
    availability_zones  = ["1", "2", "3"]
    vnet_subnet_id      = azapi_resource.subnet_nodes.id
    node_taints         = ["CriticalAddonsOnly=true:NoSchedule"]
    upgrade_settings    = { max_surge = "33%" }
  }

  # Platform pool: everything Argo CD deploys.
  agent_pools = {
    platform = {
      name                = "platform"
      mode                = "User"
      vm_size             = var.platform_pool.vm_size
      enable_auto_scaling = true
      min_count           = var.platform_pool.min_count
      max_count           = var.platform_pool.max_count
      availability_zones  = ["1", "2", "3"]
      vnet_subnet_id      = azapi_resource.subnet_nodes.id
      upgrade_settings    = { max_surge = "33%" }
    }
  }

  # Patches and node images apply automatically, inside the maintenance
  # window; minor versions are a reviewed change to kubernetes_version.
  auto_upgrade_profile = {
    upgrade_channel         = "patch"
    node_os_upgrade_channel = "NodeImage"
  }
  maintenanceconfiguration = {
    aksManagedAutoUpgradeSchedule = {
      name = "aksManagedAutoUpgradeSchedule"
      maintenance_window = {
        duration_hours = 4
        start_time     = "02:00"
        utc_offset     = "+00:00"
        schedule       = { weekly = { day_of_week = "Sunday", interval_weeks = 1 } }
      }
    }
    aksManagedNodeOSUpgradeSchedule = {
      name = "aksManagedNodeOSUpgradeSchedule"
      maintenance_window = {
        duration_hours = 4
        start_time     = "02:00"
        utc_offset     = "+00:00"
        schedule       = { weekly = { day_of_week = "Saturday", interval_weeks = 1 } }
      }
    }
  }

  addon_profile_oms_agent = {
    enabled = true
    config = {
      log_analytics_workspace_resource_id = azapi_resource.log_analytics.id
      use_aad_auth                        = true
    }
  }

  depends_on = [azapi_resource.cluster_network_contributor]
}
