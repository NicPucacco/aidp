# ADR-0009: Tenant PRs are rendered and policy-checked before review

- **Status:** Accepted
- **Date:** 2026-10-07
- **Phase:** v3-service-path

## Context

ADR-0001 makes humans the final gate on every change. That only scales if
reviewers aren't doing mechanical work. For a tenant PR the mechanical
questions are:

- Is it within the tenant boundary (ADR-0007)?
- Does it compose? A typo in a size or a bad field fails at sync time, after merge.
- Does what it composes into pass the baseline policies (ADR-0005)?

The last one is subtle. Policies apply to *composed* resources (Deployments),
but tenants write *XRs* (WebService). Running Kyverno over the tenant's YAML
checks nothing useful.

This matters more in v5. Agents will open PRs faster than humans can review
them, and the platform needs to tell an agent "this fails, and here's why"
without a human in the loop.

## Decision

`scripts/check-tenants.py` runs in CI on every PR, in three steps:

1. **Boundary:** only `platform.fernhill.io` kinds; `metadata.namespace`
   must not be set (this closes the gap noted in ADR-0007).
2. **Render:** each object goes through its real Composition with
   `crossplane render`, which runs the same function-python package the
   cluster runs.
3. **Policy:** the rendered resources are evaluated with `kyverno apply`
   against `platform/policies/`, with each team namespace labelled the way
   the ApplicationSet labels it.

Failures are specific (`tenants/x/y.yaml: metadata.namespace must not be set`)
and land on the PR before any reviewer sees it.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Rely on admission at sync time | Correct but late: the author finds out after merge, from an Argo CD error. |
| Kyverno policies written against XRs | Doubles the policy set and drifts from what's actually enforced on workloads. |
| Server-side dry-run against a shared cluster | Needs cluster credentials in CI (contradicts ADR-0001's "nothing writes to clusters but Argo CD") and depends on cluster state. |
| Unit tests on `compose.py` only | Those check the platform's code. This checks the tenant's input against it. Both are needed. |

## Consequences

- Reviewers of tenant PRs judge intent ("should Billing have a large
  database?"), not syntax or compliance.
- CI needs Docker to render, since function-python runs as a container.
  That's fine on GitHub-hosted runners.
- The Crossplane CLI now ships on its own release train, so it can't be
  derived from the cluster version the way the Kyverno CLI is. It's pinned to
  the nearest release (v2.4.1 for core 2.4.2), and skew is a known, small risk.
- Rendering doesn't see observed state, so readiness-dependent logic isn't
  exercised here. That's what the e2e job covers.

## What would change my mind

- Tenant count grows enough that rendering everything per PR is slow. Then
  render only changed tenant directories.
- Kyverno gains first-class support for evaluating XRs through their
  compositions, which would make the render step redundant.
