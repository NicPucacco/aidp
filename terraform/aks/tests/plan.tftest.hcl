# Offline plan tests with mocked providers: no Azure credentials or spend.
# They check our inputs, wiring, and the module's own validations, not that
# Azure accepts the request; that's what a real `plan` in a pipeline does.
#   terraform -chdir=terraform/aks init -backend=false && terraform -chdir=terraform/aks test

mock_provider "azapi" {
  mock_data "azapi_client_config" {
    defaults = {
      subscription_id = "00000000-0000-0000-0000-000000000001"
      tenant_id       = "00000000-0000-0000-0000-000000000002"
      object_id       = "00000000-0000-0000-0000-000000000003"
    }
  }
}

mock_provider "random" {}
mock_provider "azuread" {}

variables {
  api_server_authorized_ip_ranges = ["203.0.113.0/24"]
  admin_group_object_ids          = ["00000000-0000-0000-0000-000000000004"]
  base_domain                     = "platform.fernhill.example"
  acme_email                      = "platform-team@fernhill.example"
  sso_admins_group_object_id      = "00000000-0000-0000-0000-00000000000d"
  sso_engineers_group_object_id   = "00000000-0000-0000-0000-00000000000e"
}

run "plans_with_defaults" {
  command = plan

  assert {
    condition     = azapi_resource.resource_group.name == "rg-fernhill-prod"
    error_message = "Resource group should be named rg-<prefix>-<environment>."
  }

  assert {
    condition     = azapi_resource.subnet_nodes.body.properties.addressPrefix == "10.40.1.0/24"
    error_message = "Node subnet should be the second /24 of the VNet."
  }

  assert {
    condition     = azapi_resource.resource_group.tags["managed-by"] == "terraform"
    error_message = "Every resource should be tagged managed-by=terraform."
  }
}

run "emits_the_environment_the_platform_expects" {
  command = plan

  # Same shape as `environment` in platform/apps/values.yaml (ADR-0017).
  assert {
    condition = (
      toset(keys(output.platform_environment)) == toset(["name", "baseDomain", "urlPort", "gateway", "tls", "sso"]) &&
      toset(keys(output.platform_environment.sso)) == toset(["enabled", "tenantID", "argocdClientID", "portalClientID", "adminsGroupID", "engineersGroupID"]) &&
      toset(keys(output.platform_environment.gateway)) == toset(["serviceType", "ipv4", "resourceGroup"]) &&
      toset(keys(output.platform_environment.tls)) == toset(["enabled", "acmeEmail", "acmeServer", "azureDNS"]) &&
      toset(keys(output.platform_environment.tls.azureDNS)) == toset(["subscriptionID", "resourceGroup", "zone", "clientID"])
    )
    error_message = "platform_environment must match the environment block in platform/apps/values.yaml."
  }

  assert {
    condition = (
      output.platform_environment.gateway.serviceType == "LoadBalancer" &&
      output.platform_environment.tls.enabled &&
      output.platform_environment.baseDomain == "platform.fernhill.example"
    )
    error_message = "AKS environment should use a LoadBalancer Gateway with TLS on the base domain."
  }

  assert {
    condition     = azapi_resource.wildcard_record.name == "*" && azapi_resource.dns_zone.name == "platform.fernhill.example"
    error_message = "A wildcard record in the base domain's zone should point at the Gateway."
  }

  assert {
    condition     = azapi_resource.cert_manager_federation.body.properties.subject == "system:serviceaccount:cert-manager:cert-manager"
    error_message = "cert-manager's identity must only trust its own ServiceAccount."
  }
}

run "sso_trusts_exactly_one_service_account_per_app" {
  command = plan

  assert {
    condition = (
      azuread_application_federated_identity_credential.sso["argocd"].subject == "system:serviceaccount:argocd:argocd-server" &&
      azuread_application_federated_identity_credential.sso["portal"].subject == "system:serviceaccount:backstage:oauth2-proxy"
    )
    error_message = "Each SSO app must trust only the ServiceAccount that signs users in."
  }

  assert {
    condition     = alltrue([for sp in azuread_service_principal.sso : sp.app_role_assignment_required])
    error_message = "Entra must refuse sign-in to anyone not in an assigned group."
  }

  assert {
    condition     = length(azuread_app_role_assignment.sso) == 4
    error_message = "Both groups should be assigned to both apps."
  }

  assert {
    condition     = one(azuread_application.sso["portal"].web[0].redirect_uris) == "https://backstage.platform.fernhill.example/oauth2/callback"
    error_message = "The portal's redirect URI must be its oauth2-proxy callback on the base domain."
  }
}

run "rejects_an_unrestricted_api_server_by_omission" {
  command = plan

  variables {
    api_server_authorized_ip_ranges = []
  }

  expect_failures = [var.api_server_authorized_ip_ranges]
}
