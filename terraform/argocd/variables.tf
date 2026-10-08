variable "kubeconfig_path" {
  description = "Path to the kubeconfig file for the target cluster."
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "Kubeconfig context to install into. Any conformant cluster works (ADR-0004)."
  type        = string
}

variable "repo_url" {
  description = "Git repository Argo CD reconciles from."
  type        = string
  default     = "https://github.com/NicPucacco/aidp.git"
}

variable "target_revision" {
  description = "Branch, tag, or commit Argo CD tracks. Point at a phase tag (e.g. v1-gitops-core) to replay history."
  type        = string
  default     = "main"
}

variable "argocd_chart_version" {
  description = "argo/argo-cd Helm chart version. Day 0 only; from v1 Argo CD manages its own upgrades."
  type        = string
  default     = "10.9.6"
}

variable "argocd_apps_chart_version" {
  description = "argo/argocd-apps Helm chart version, used to create the root Application."
  type        = string
  default     = "2.0.6"
}
