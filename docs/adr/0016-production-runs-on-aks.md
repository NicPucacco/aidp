# ADR-0016: Production runs on AKS, provisioned with the Azure Verified Module

- **Status:** Accepted
- **Date:** 2026-10-07
- **Phase:** infra (after v5-agentic)

## Context

Until now the platform only ran locally (kind) and in CI, by design
(ADR-0004): the abstractions had to be proven before choosing where they
live. Fernhill has now chosen Azure. The platform needs a production cluster
that's reproducible, reviewable, and secure by default, and it must keep
running unchanged on kind for development and CI.

## Decision

**1. AKS, defined in `terraform/aks/` with
[`Azure/avm-res-containerservice-managedcluster`](https://registry.terraform.io/modules/Azure/avm-res-containerservice-managedcluster/azurerm)
(Azure Verified Module, pinned to 0.8.3).**

**2. Two root modules, two states.** `terraform/aks` owns the cluster and what
it needs to exist (resource group, VNet, identity, Log Analytics).
`terraform/argocd` (moved from `bootstrap/terraform`) still owns only day 0,
against *any* kubeconfig, so local kind keeps working (ADR-0003, ADR-0004).
The cluster's lifecycle is rare and high-impact, so it doesn't share a plan
with anything else.

**3. Secure and boring defaults, each an explicit input:**

| Choice | Why |
|---|---|
| Entra ID + Azure RBAC, **local accounts disabled** | No static kubeconfig credentials exist to leak; access is an Entra group (`admin_group_object_ids`) |
| API server restricted to `api_server_authorized_ip_ranges`, **required, no default** | An open API server must be a deliberate, reviewed value; the variable refuses an empty list (tested) |
| OIDC issuer + workload identity | Crossplane, External Secrets, and the agent's GitHub App key can reach Azure without stored secrets |
| Azure CNI overlay + Cilium dataplane | Nodes take subnet IPs, pods don't; network policy and observability without a separate CNI |
| Tainted system pool + autoscaling `platform` pool (2–5 × D4s_v6) | AKS add-ons are isolated; the pool is sized from what the full stack actually needed (12 GB, v4) |
| Patch + node-image auto-upgrade in a weekly maintenance window | Security patches without a ticket; **minor** upgrades stay a reviewed change to `kubernetes_version` |
| Standard tier (uptime SLA), zones 1–3 | It's production |
| Container Insights to Log Analytics (30 days) | Baseline observability without adding to the platform team's stack yet |

**4. Tested offline.** `terraform test` plans against mocked providers in CI
(naming, CIDR maths, input validation, module validations). No Azure
credentials live in CI yet.

## Alternatives considered

| Option | Why not |
|---|---|
| `Azure/aks/azurerm` (the classic module) | **Being retired**: its README carries a deprecation notice (bug fixes only, then retirement) and points to the AVM module; its last release was May 2026. Starting on a retired module is starting with a migration. |
| Raw `azurerm_kubernetes_cluster` | Possible, but AVM encodes Microsoft's WAF-aligned defaults and is maintained against the API. Fernhill's 4-person team shouldn't own that surface. |
| Crossplane provisions AKS | Chicken-and-egg: you need a cluster running Crossplane first. Right for a fleet of workload clusters later (ADR-0003). |
| One root module for cluster + Argo CD | One plan that can replace a cluster and reinstall Argo CD in the same apply. Different lifecycles, different blast radius. |
| Private cluster from day one | Better posture, but needs a VNet-connected runner or bastion for every `kubectl` and for Argo CD bootstrap. The module supports it (`enable_private_cluster`). It's the next step once there's a deployment pipeline inside the network. |

## Consequences

- **What's *not* done yet, and what the platform needs before tenants run on AKS:**
  1. ~~**Ingress:**~~ done in [ADR-0017](0017-ingress-per-environment.md): static
     IP, Azure DNS wildcard, and Let's Encrypt via cert-manager, all driven by one
     environment object from Terraform.
  2. **Database backups:** CloudNativePG to Blob Storage via workload identity,
     or an Azure Database for PostgreSQL composition behind the same `Database`
     API, which the API was designed for (ADR-0006).
  3. **Human SSO:** Argo CD and Backstage still use local admin and guest auth.
     Entra ID for both.
  4. **Secrets:** the agent's GitHub App key and any future secrets go to
     Key Vault via External Secrets and workload identity.
  5. **A deployment pipeline** with OIDC federation to Azure, running
     `plan` on PRs and `apply` on approval. Until then, `make aks-plan` and
     `make aks-apply` are run by a platform engineer.
- **Cost:** two D2s_v6 system nodes, two to five D4s_v6 platform nodes, the
  Standard tier, and Log Analytics. Expect a few hundred US dollars a month
  at minimum scale; verify with the Azure pricing calculator for the chosen
  region before applying.
- **ADR-0004 still holds.** Nothing in `platform/` is AKS-specific. The
  Gateway change above is a per-environment value, not a fork.

## What would change my mind

- More than one production cluster (regions, isolation). Then a management
  cluster with Crossplane or Cluster API provisioning workload clusters
  beats a Terraform root module per cluster.
- The organisation adopts a landing-zone module set (hub-spoke networking,
  shared Log Analytics). Then `terraform/aks` consumes those instead of
  creating its own VNet and workspace.
