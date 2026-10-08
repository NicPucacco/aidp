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

variables {
  api_server_authorized_ip_ranges = ["203.0.113.0/24"]
  admin_group_object_ids          = ["00000000-0000-0000-0000-000000000004"]
  base_domain                     = "platform.fernhill.example"
  acme_email                      = "platform-team@fernhill.example"
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
      toset(keys(output.platform_environment)) == toset(["name", "baseDomain", "urlPort", "gateway", "tls"]) &&
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

run "rejects_an_unrestricted_api_server_by_omission" {
  command = plan

  variables {
    api_server_authorized_ip_ranges = []
  }

  expect_failures = [var.api_server_authorized_ip_ranges]
}
