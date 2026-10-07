terraform {
  required_version = ">= 1.9"

  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"
    }
  }

  # Local state on purpose: bootstrap is idempotent and recoverable by
  # re-running it. In production this would be a remote backend (see ADR-0003).
}
