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

output "next_steps" {
  value = <<-EOT
    Cluster ${module.aks.name} is up. Install the platform onto it:

      az aks get-credentials -g ${azapi_resource.resource_group.name} -n ${module.aks.name}
      kubelogin convert-kubeconfig -l azurecli
      make platform KUBE_CONTEXT=${module.aks.name}

    Local accounts are disabled: access is via your Entra group in admin_group_object_ids.
  EOT
}
