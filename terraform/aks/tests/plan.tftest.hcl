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

run "rejects_an_unrestricted_api_server_by_omission" {
  command = plan

  variables {
    api_server_authorized_ip_ranges = []
  }

  expect_failures = [var.api_server_authorized_ip_ranges]
}
