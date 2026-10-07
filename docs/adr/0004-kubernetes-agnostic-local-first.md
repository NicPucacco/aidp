# ADR-0004: Kubernetes-agnostic, local-first

- **Status:** Accepted
- **Date:** 2026-10-06
- **Phase:** v0-foundations

## Context

Fernhill's platform team was told "no new cloud spend to prove the idea" and
already runs clusters that were set up separately by different teams. The
platform has to work on whatever Kubernetes is available.

Separately, this repository is meant to be run by people evaluating it, and
asking a reviewer to create cloud accounts is a fast way to make sure nobody runs it.

## Decision

**The platform targets the Kubernetes API, not a distribution.** It must install
onto any conformant cluster (kind, k3d, Docker Desktop, minikube, EKS, GKE, AKS)
given only a kubeconfig context.

Rules that follow from this:

1. **No distribution-specific resources in `platform/`.** No `kind`-only port
   mappings, no cloud load balancer annotations, no assumed CSI driver names.
2. **Gateway API for ingress**, implemented by Envoy Gateway. It's the portable
   standard. ingress-nginx, the old de-facto default, was retired in March 2026.
3. **Cluster-specific facts are inputs, not assumptions.** Storage class,
   whether `LoadBalancer` services get an address, and the base domain are
   Terraform variables / Helm values with sensible defaults.
4. **Local-first defaults.** `make up` creates a kind cluster because it's the
   most widely available option. `make platform KUBE_CONTEXT=<ctx>` skips cluster
   creation and installs onto any existing cluster.
5. **Cloud-specific code lives behind an abstraction boundary.** The `Database`
   API (v2) has a local composition (CloudNativePG) and a documented cloud
   composition (RDS). The developer-facing API is identical; only the
   platform-side composition differs.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Target one cloud (e.g. EKS + RDS + ALB) | Most realistic for a single employer, but reviewers can't run it and it couples the story to one vendor. |
| Target kind only and use its conveniences | Faster to build, but then "agnostic" is a claim nothing tests. |
| Ingress API + ingress-nginx | Retired upstream. Choosing it now would be choosing a migration. |

## Consequences

- Reaching services locally needs a small, explicit step (`make ui` port-forwards)
  rather than relying on a `LoadBalancer` IP that only some local tools provide.
- CI can test the full platform on a throwaway kind cluster in GitHub Actions,
  which is the same thing a reviewer does.
- Some things are less impressive locally than in a cloud (no real RDS, no real
  DNS). The abstraction is what's being demonstrated, and that's the part that
  transfers to any employer's stack.

## What would change my mind

- Fernhill standardises on one cloud and the cost of keeping compositions
  portable exceeds its benefit. Portability for its own sake is not a goal.
  Portability *of the developer-facing API* is.
