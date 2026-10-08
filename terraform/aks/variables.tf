variable "location" {
  description = "Azure region. Must support availability zones."
  type        = string
  default     = "eastus2"
}

variable "name_prefix" {
  description = "Prefix for resource names, e.g. rg-<prefix>-<environment>."
  type        = string
  default     = "fernhill"
}

variable "environment" {
  description = "Environment name used in resource names and tags."
  type        = string
  default     = "prod"
}

variable "kubernetes_version" {
  description = "AKS minor version (e.g. \"1.35\"). Null uses AKS's default; patches are applied automatically either way."
  type        = string
  default     = null
}

variable "api_server_authorized_ip_ranges" {
  description = "CIDRs allowed to reach the Kubernetes API (office/VPN egress, CI runners). Required: an open API server is a choice someone should make explicitly."
  type        = list(string)

  validation {
    condition     = length(var.api_server_authorized_ip_ranges) > 0
    error_message = "Set at least one CIDR. To allow everyone, pass [\"0.0.0.0/0\"] and own that decision in review."
  }
}

variable "admin_group_object_ids" {
  description = "Microsoft Entra group object IDs that get AKS RBAC Cluster Admin. Local accounts are disabled, so this is the only way in."
  type        = list(string)
}

variable "vnet_address_space" {
  description = "Address space for the cluster's virtual network."
  type        = string
  default     = "10.40.0.0/16"
}

variable "system_pool" {
  description = "System node pool: tainted CriticalAddonsOnly, runs only AKS add-ons."
  type = object({
    vm_size   = string
    min_count = number
    max_count = number
  })
  default = {
    vm_size   = "Standard_D2s_v6"
    min_count = 2
    max_count = 3
  }
}

variable "platform_pool" {
  description = "User node pool for the platform (Argo CD, Crossplane, Kyverno, Backstage) and tenant workloads."
  type = object({
    vm_size   = string
    min_count = number
    max_count = number
  })
  # The full platform needed ~12 GB to converge on one node (README); two
  # 16 GB nodes leave room for tenants and for a node to drain.
  default = {
    vm_size   = "Standard_D4s_v6"
    min_count = 2
    max_count = 5
  }
}

variable "tags" {
  description = "Extra tags for every resource."
  type        = map(string)
  default     = {}
}

variable "base_domain" {
  description = "DNS zone the platform serves under, e.g. platform.fernhill.example. Hosts are <name>.<base_domain>. Delegate it from the parent zone using the name_servers output."
  type        = string
}

variable "acme_email" {
  description = "Contact address for Let's Encrypt (expiry and policy notices)."
  type        = string
}

variable "sso_admins_group_object_id" {
  description = "Entra group whose members get Argo CD admin and portal access (the platform team)."
  type        = string
}

variable "sso_engineers_group_object_id" {
  description = "Entra group whose members get read-only Argo CD and portal access (all engineers)."
  type        = string
}
