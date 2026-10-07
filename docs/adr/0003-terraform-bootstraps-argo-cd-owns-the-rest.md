# ADR-0003: Terraform bootstraps Argo CD; Argo CD owns everything after

- **Status:** Accepted
- **Date:** 2026-10-06
- **Phase:** v0-foundations

## Context

Something has to install the thing that installs everything else. Terraform and
Argo CD both *can* install Helm charts and Kubernetes manifests, so without a
clear boundary they end up fighting over the same resources: Terraform plans
show drift that Argo CD caused, and Argo CD reverts changes Terraform made.

Fernhill also wants the platform to run on **any conformant Kubernetes
cluster** (see [ADR-0004](0004-kubernetes-agnostic-local-first.md)), so the
bootstrap can't assume EKS, GKE, or a specific local tool.

## Decision

**Terraform's job ends when Argo CD is running and pointed at this repo.**

Terraform (in `bootstrap/terraform/`) does exactly three things, using only the
`helm` provider against a kubeconfig context:

1. Installs Argo CD (Helm chart, pinned version).
2. Installs a single root `Application` (via the `argocd-apps` chart) pointing at
   `platform/`.
3. Outputs how to reach the Argo CD UI.

Everything else, including Crossplane, Kyverno, the gateway, Backstage, and
Argo CD's own configuration after day 0, is an Argo CD `Application` under
`platform/`.

**Ownership rule:** a resource is managed by exactly one tool. If Argo CD
manages it, it is not in Terraform state. The one handoff is Argo CD itself:
Terraform installs it once, and from v1 the root app also manages the Argo CD
chart, so upgrades go through Git like everything else.

### Why `argocd-apps` instead of `kubernetes_manifest`

The `kubernetes_manifest` resource needs the `Application` CRD to exist **at
plan time**, so a fresh cluster fails to plan. Wrapping the root Application in
the official `argocd-apps` Helm chart avoids this: Helm doesn't validate CRDs at
plan time, and `depends_on` orders the install. It's a small detail, but it's
the most common reason Terraform bootstrap code falls back on `local-exec kubectl`.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Terraform manages everything (Argo CD optional) | Every platform change becomes a `terraform apply` by someone with cluster-admin. This contradicts ADR-0001. |
| Shell script + `kubectl apply` | Works on day 0, but nothing declares or detects drift in the bootstrap itself. |
| `idpbuilder` / similar all-in-one bootstrappers | Great for demos; hides exactly the decisions this repo exists to show. |
| Crossplane provisions the cluster *and* bootstraps Argo CD | Chicken-and-egg: you need a cluster running Crossplane first. Right for a fleet, overkill for one cluster. |

## Consequences

- `terraform apply` is rare: initial bootstrap, or recovering a lost cluster.
  Day-to-day work never touches Terraform.
- Disaster recovery is "new cluster → `terraform apply` → wait for Argo CD to
  converge," which is easy to test because it's exactly what `make up` does locally.
- Terraform state for bootstrap is small and low-risk. Locally it's a file; in
  production it would be a remote backend, but nothing in it is a secret beyond
  the generated Argo CD admin password, which should be rotated or disabled in favour of SSO.

## What would change my mind

- Running many clusters. Then a management cluster with Argo CD
  (or Crossplane) bootstrapping workload clusters beats per-cluster Terraform.
- A cloud provider offering managed Argo CD (e.g. EKS Capabilities) that we
  standardise on. Then bootstrap becomes "enable the add-on".
