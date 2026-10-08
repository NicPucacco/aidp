# Sign-in with Microsoft Entra ID for Argo CD and the portal (ADR-0018).
#
# No client secrets: each app registration trusts exactly one Kubernetes
# ServiceAccount in this cluster (workload identity federation), so there is
# nothing to store, rotate, or leak. Entra itself enforces who may sign in
# (assignment required), before any app-level RBAC.

locals {
  # Entra's "default access" app role, used for group assignments to apps
  # that don't define roles of their own.
  default_app_role = "00000000-0000-0000-0000-000000000000"
  sso_groups = {
    admins    = var.sso_admins_group_object_id
    engineers = var.sso_engineers_group_object_id
  }
  sso_apps = {
    argocd = {
      display_name    = "Fernhill Argo CD (${var.environment})"
      redirect_uri    = "https://argocd.${var.base_domain}/auth/callback"
      service_account = "system:serviceaccount:argocd:argocd-server"
    }
    portal = {
      display_name    = "Fernhill Developer Portal (${var.environment})"
      redirect_uri    = "https://backstage.${var.base_domain}/oauth2/callback"
      service_account = "system:serviceaccount:backstage:oauth2-proxy"
    }
  }
  sso_assignments = {
    for pair in setproduct(keys(local.sso_apps), keys(local.sso_groups)) :
    "${pair[0]}-${pair[1]}" => { app = pair[0], group = pair[1] }
  }
}

resource "azuread_application" "sso" {
  for_each = local.sso_apps

  display_name     = each.value.display_name
  sign_in_audience = "AzureADMyOrg"
  # Puts the user's security groups in the ID token; Argo CD RBAC and
  # oauth2-proxy's --allowed-group both read it.
  group_membership_claims = ["SecurityGroup"]

  web {
    redirect_uris = [each.value.redirect_uri]
  }

  # `argocd login --sso` completes on a local callback.
  dynamic "public_client" {
    for_each = each.key == "argocd" ? [1] : []
    content {
      redirect_uris = ["http://localhost:8085/auth/callback"]
    }
  }
}

resource "azuread_service_principal" "sso" {
  for_each = local.sso_apps

  client_id = azuread_application.sso[each.key].client_id
  # Only assigned groups may sign in at all; enforced by Entra, not the app.
  app_role_assignment_required = true
}

resource "azuread_app_role_assignment" "sso" {
  for_each = local.sso_assignments

  app_role_id         = local.default_app_role
  principal_object_id = local.sso_groups[each.value.group]
  resource_object_id  = azuread_service_principal.sso[each.value.app].object_id
}

resource "azuread_application_federated_identity_credential" "sso" {
  for_each = local.sso_apps

  application_id = azuread_application.sso[each.key].id
  display_name   = "aks-${local.suffix}-${each.key}"
  description    = "Workload identity for ${each.value.service_account} on aks-${local.suffix}"
  audiences      = ["api://AzureADTokenExchange"]
  issuer         = module.aks.oidc_issuer_profile_issuer_url
  subject        = each.value.service_account
}
