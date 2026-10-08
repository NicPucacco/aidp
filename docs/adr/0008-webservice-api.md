# ADR-0008: The WebService API: safe defaults decided once

- **Status:** Accepted
- **Date:** 2026-10-07
- **Phase:** v3-service-path

## Context

Fernhill deploys 14 services 14 ways ([story, problem #2](../story.md#what-hurts-the-before-picture)).
About half have resource limits, probes, or ownership labels. None share a
security posture. Every team re-learns the same Kubernetes details, and
on-call can't predict what any given service looks like.

v1 made the baseline *enforceable* (ADR-0005). v2 showed the platform API
pattern (ADR-0006). v3 applies that pattern to the thing every team ships most:
a long-running HTTP service.

## Decision

### 1. A small API for an HTTP service

```yaml
apiVersion: platform.fernhill.io/v1alpha1
kind: WebService
metadata:
  name: invoice-api
spec:
  image: ghcr.io/fernhill/invoice-api:1.4.2   # pinned; schema rejects :latest
  port: 9898
  healthPath: /readyz
  replicas: 2
  expose: true              # -> https://invoice-api-billing.<domain> (ADR-0017)
  database: invoice-api     # -> DATABASE_URL + PG* from the Database's secret
```

### 2. The composition decides everything else, once

| Every WebService gets | Why it's not a tenant choice |
|---|---|
| Requests + memory limit from a t-shirt size | Matches the baseline policy; teams pick a size, not numbers |
| Readiness and liveness probes on `healthPath` | Safe rolling updates |
| Non-root fixed UID, read-only root FS, all capabilities dropped, `RuntimeDefault` seccomp, writable `/tmp` | One reviewed security posture instead of 14 |
| A PodDisruptionBudget and spread across nodes when `replicas > 1` | Node drains don't take a service down |
| Ownership labels from the team namespace | On-call can find the owner from the workload |
| A route on the shared Gateway when `expose: true` | No per-team ingress config |

### 3. Bind to a Database by reference, never by copy

`database: invoice-api` injects `DATABASE_URL` and `PG*` variables as
`secretKeyRef`s to the Database's secret (`status.connectionSecret`, ADR-0006).
Credentials never appear in the WebService, the Deployment spec, or Git.

### 4. Named `WebService`

It was first planned as `Service`, which collides with the core `Service`
(`svc`). The first implementation was named `App`, which collided with Argo
CD's `Application` short names (`app`, `apps`). `kubectl get app` silently
returned Argo CD objects, so it looked like the platform had no apps.
`WebService` collides with nothing. Lesson: check `kubectl api-resources` on a
real cluster before naming a kind, because short names from installed CRDs
count too.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| A shared Helm chart that teams values-override | Teams can override anything, so the "defaults" are suggestions. There's also no status, no readiness, and no API to version. |
| Expose raw Deployments with policies as the only guardrail | Policies say *no*. They don't write the probe or the PDB for you. And it's a large API surface to give an agent (ADR-0007). |
| Knative / KubeVela / Score | Credible. KubeVela and Score in particular model exactly this. They'd be a reasonable choice at a bigger org. Here they add another control plane for a 4-person team that already runs Crossplane for databases; one composition engine for both APIs is simpler. |
| Let images run as their own declared user | Images with a named `USER` can't be verified as non-root by the kubelet. A fixed UID is enforceable; the cost is that a few images need a writable path or ownership fix. |

## Consequences

- A new HTTP service is about 10 lines of YAML, and it's compliant by construction.
- **Some images won't run unmodified** (fixed UID, read-only FS). That's the right
  default. A team with a genuine need asks for a field (e.g. extra writable
  volumes), which becomes visible platform backlog.
- No autoscaling, no secrets other than the database's, no sidecars, no
  non-HTTP ports yet. Each is a deliberate future field, added when a team needs it.
- The platform now owns a security posture for every paved-road workload. A CVE
  in, say, the default seccomp handling becomes one PR to the WebService composition.

## What would change my mind

- Teams routinely need more than ~15 fields. Then the abstraction is too thin
  and Score/KubeVela-style specs earn their place.
- The fixed-UID rule blocks more than ~1 in 5 services trying to migrate. Then
  make the UID an input, constrained by policy instead of fixed.
