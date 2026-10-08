terraform {
  required_version = ">= 1.11, < 2.0"

  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.9"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
    # Entra ID app registrations for SSO (Microsoft Graph). The identity
    # running apply needs Application.ReadWrite.OwnedBy and
    # AppRoleAssignment.ReadWrite.All.
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.10"
    }
  }

  # Remote state in Azure Storage, configured at init time so no account
  # names live in Git:  terraform init -backend-config=backend.hcl
  # (see backend.hcl.example). CI validates with -backend=false.
  backend "azurerm" {}
}

# Both authenticate like the Azure CLI: `az login` locally, OIDC federation in CI.
provider "azapi" {}
provider "azuread" {}
