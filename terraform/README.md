# terraform/

Two root modules, two states, applied in order. Each owns one layer and
nothing else (ADR-0003, ADR-0016).

| Module | Owns | Changes | State |
|---|---|---|---|
| [`aks/`](aks) | The production AKS cluster and its edge: resource group, network, identity, logging, Gateway IP, DNS zone, cert-manager identity | Rarely (cluster upgrades, node pool sizing) | Azure Storage (`backend.hcl`) |
| [`argocd/`](argocd) | Day 0 on *any* cluster: installs Argo CD and the root app, then stops | Almost never; Argo CD manages itself after | Local, or a backend per cluster |

Everything *on* the cluster after day 0 is Argo CD reconciling `platform/`
from Git. Neither module touches it.

## Production (AKS)

```bash
# Needs: Contributor + User Access Administrator on the subscription, and
# Microsoft Graph Application.ReadWrite.OwnedBy + AppRoleAssignment.ReadWrite.All
# (Entra app registrations for SSO, ADR-0018).
az login
cp terraform/aks/backend.hcl.example terraform/aks/backend.hcl          # state storage
cp terraform/aks/terraform.tfvars.example terraform/aks/terraform.tfvars # CIDRs, admin group
make aks-plan      # review the plan
make aks-apply     # apply exactly what was reviewed

# One-time: delegate base_domain from its parent zone to these name servers.
terraform -chdir=terraform/aks output name_servers

az aks get-credentials -g rg-fernhill-prod -n aks-fernhill-prod
kubelogin convert-kubeconfig -l azurecli
make platform-aks  # passes terraform/aks's platform_environment to Argo CD
```

`platform_environment` is the one object that makes the same `platform/`
behave differently on AKS: domain, the Gateway's static IP, and TLS settings
(ADR-0017). It's generated, never committed.

## Local (kind)

```bash
make up    # kind cluster + terraform/argocd, no Azure needed
```

## Tests

`make aks-test` plans the AKS module against **mocked providers**, so it
needs no Azure credentials and costs nothing. It checks naming, network
maths, and input validation, including refusing an API server with no
authorized IP ranges. CI runs it on every PR. A real `plan` against Azure is
the job of a deployment pipeline with OIDC federation, which is a follow-up
(ADR-0016).
