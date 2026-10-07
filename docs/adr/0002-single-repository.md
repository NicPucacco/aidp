# ADR-0002: One repository for platform and tenant config, for now

- **Status:** Accepted
- **Date:** 2026-10-06
- **Phase:** v0-foundations

## Context

A GitOps setup usually involves at least three kinds of content:

1. **Platform definitions:** Crossplane XRDs and compositions, Kyverno policies,
   shared Helm charts, the Argo CD app-of-apps. Owned by the platform team and changed rarely.
2. **Tenant config:** "Billing wants a service called `invoice-api` with a
   small Postgres." Written by developers and agents, and changed often.
3. **Bootstrap:** the minimum needed to get Argo CD running on a cluster.

These could live in one repo or be split. Most mature setups split at least (1)
from (2).

## Decision

**Keep everything in one repository, separated by directory and enforced by CODEOWNERS:**

```
bootstrap/   # day-0: Terraform that installs Argo CD on any cluster
platform/    # platform team: APIs, policies, charts, Argo apps
tenants/     # developers + agents: one directory per team/service
```

- `platform/**` and `bootstrap/**` require platform-team review.
- `tenants/<team>/**` requires that team's review.
- Agent PRs may only touch `tenants/**`. CI enforces this (see ADR-0001).

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Split `platform` and `tenants` into two repos | The right end state for a larger org. At Fernhill's size it adds cross-repo version coordination before there's anything to coordinate. |
| One repo per team | Fourteen repos for fourteen services, each needing CI and policy wiring. It would recreate problem #2 ("fourteen ways to deploy"). |
| Argo CD config in its own repo | Separates the thing that deploys from what it deploys, but you need both to understand any change. |

## Consequences

- One clone, one CI config, one place to read history. This matters for a
  4-person platform team, and for anyone evaluating this repository.
- A PR can change an API *and* its first consumer at the same time, which keeps
  early-stage platform iteration fast.
- Blast radius is wider: a bad merge to `platform/` touches everyone. CODEOWNERS
  and CI policy gates are the mitigation, not repository boundaries.
- Argo CD polls one repo, so every commit triggers reconciliation checks for every app.
  Not a concern at this scale.

## What would change my mind

I would split `tenants/` into its own repository when **any** of these become true:

- The platform team needs to version platform APIs independently. For example,
  tenants pin to `Database` API v1 while v2 is in beta. A separate repo makes
  "which version of the platform does this tenant use" explicit.
- PR volume in `tenants/` (agents especially) makes `platform/` changes hard to
  find or review.
- Argo CD repo-server or webhook load becomes measurable.
- A compliance boundary requires different access controls on platform code vs.
  tenant config.

The directory layout is chosen so that split is a `git filter-repo` and one
Argo CD `repoURL` change, not a redesign.
