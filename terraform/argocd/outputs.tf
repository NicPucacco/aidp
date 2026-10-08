output "argocd_namespace" {
  value = local.argocd_namespace
}

output "next_steps" {
  value = <<-EOT
    Argo CD is installed and tracking ${var.repo_url}@${var.target_revision} (platform/apps).

      make ui        # port-forward the Argo CD UI to http://localhost:8080
      make password  # print the initial admin password
  EOT
}
