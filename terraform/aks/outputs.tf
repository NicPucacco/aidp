output "resource_group" {
  value = azapi_resource.resource_group.name
}

output "cluster_name" {
  value = module.aks.name
}

output "oidc_issuer_url" {
  description = "For workload identity federation (Crossplane, External Secrets, the agent's GitHub App key)."
  value       = module.aks.oidc_issuer_profile_issuer_url
}

output "name_servers" {
  description = "Delegate base_domain to these from the parent zone (one-time, outside this module)."
  value       = azapi_resource.dns_zone.output.properties.nameServers
}

# Exactly the `environment` block platform/apps expects (ADR-0017).
# terraform/argocd passes it through untouched: `make platform-aks`.
output "platform_environment" {
  value = {
    name       = var.environment
    baseDomain = var.base_domain
    urlPort    = ""
    gateway = {
      serviceType   = "LoadBalancer"
      ipv4          = azapi_resource.gateway_ip.output.properties.ipAddress
      resourceGroup = azapi_resource.resource_group.name
    }
    tls = {
      enabled    = true
      acmeEmail  = var.acme_email
      acmeServer = "https://acme-v02.api.letsencrypt.org/directory"
      azureDNS = {
        subscriptionID = data.azapi_client_config.current.subscription_id
        resourceGroup  = azapi_resource.resource_group.name
        zone           = var.base_domain
        clientID       = azapi_resource.cert_manager_identity.output.properties.clientId
      }
    }
    sso = {
      enabled          = true
      tenantID         = data.azapi_client_config.current.tenant_id
      argocdClientID   = azuread_application.sso["argocd"].client_id
      portalClientID   = azuread_application.sso["portal"].client_id
      adminsGroupID    = var.sso_admins_group_object_id
      engineersGroupID = var.sso_engineers_group_object_id
    }
  }
}

output "next_steps" {
  value = <<-EOT
    Cluster ${module.aks.name} is up. Install the platform onto it:

      az aks get-credentials -g ${azapi_resource.resource_group.name} -n ${module.aks.name}
      kubelogin convert-kubeconfig -l azurecli
      make platform-aks

    Local accounts are disabled: access is via your Entra group in admin_group_object_ids.
  EOT
}
