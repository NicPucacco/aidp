# ADR-0007: The tenant boundary is a directory, a namespace, and an allow-list

- **Status:** Accepted
- **Date:** 2026-10-06
- **Phase:** v2-database-path

## Context

`tenants/` is where developers (through Backstage, v4) and AI agents (through
MCP, v5) write. Whatever a tenant directory is allowed to contain is, in effect,
the platform's public API surface. And from v5 on, that surface is reachable by agents.

Questions to answer:

1. How does a tenant's config get onto the cluster?
2. Who decides the namespace and its labels: the tenant or the platform?
3. What may a tenant declare?

## Decision

**1. One Argo CD Application per team, generated.** An ApplicationSet creates
`tenant-<team>` for every `tenants/<team>/` directory. Onboarding a team means
adding a directory (with a CODEOWNERS line). Nobody hand-writes Argo CD apps.

**2. The platform owns the namespace.** The directory name becomes the
namespace, and Argo CD's `managedNamespaceMetadata` stamps it with
`platform.fernhill.io/managed=true` and `platform.fernhill.io/owner=<team>`.
Tenants can't opt out of the baseline policies (ADR-0005) by forgetting a
label, because they never write the label.

**3. Tenants may only declare platform API objects.** The `tenants` AppProject
allows `platform.fernhill.io/*` kinds and nothing else namespaced. A raw
`Deployment`, `Role`, or `Secret` in a tenant directory fails to sync.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Let tenants write any Kubernetes resource, rely on Kyverno | Policies check *how* a resource is configured, not *whether* tenants should be creating that kind at all. And it makes the API surface "all of Kubernetes", which is too much to give an agent. |
| Namespace per service instead of per team | Better isolation, but at 60 engineers and ~14 services it multiplies RBAC, quotas, and network policies for little gain. The ApplicationSet can switch to `tenants/*/*` if that changes. |
| Tenants declare their own Namespace object | Puts the labels that control policy enforcement in tenant hands. |

## Consequences

- **The API surface is small and explicit.** That matters most in v5: an agent
  that can only open PRs against `tenants/**` and can only declare
  `platform.fernhill.io` objects has a blast radius you can explain in one sentence.
- **Escape hatches cost a platform review.** A team that needs something the
  APIs don't cover asks for it, either as a new API field or a narrowly
  scoped allow-list entry. That's friction by design, and the requests are a backlog signal.
- **The allow-list is cluster-wide per project.** Every team gets the same
  kinds. Per-team exceptions would need separate AppProjects, which isn't
  worth the complexity until a real exception shows up.
- **Known gap:** the project allows any destination namespace, so a tenant
  file with an explicit `metadata.namespace: other-team` would be applied there.
  A CI check that tenant files never set `metadata.namespace` closes this. That's
  tracked for v5, where it becomes part of the agent guardrails.

## What would change my mind

- Teams consistently need the escape hatch for the same thing. Then that thing should
  become a platform API.
- Multi-cluster: the ApplicationSet would gain a cluster generator, and the
  namespace-per-team model would need revisiting per environment.
