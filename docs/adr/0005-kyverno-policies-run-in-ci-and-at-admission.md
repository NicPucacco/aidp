# ADR-0005: Kyverno policies, evaluated in CI and at admission

- **Status:** Accepted
- **Date:** 2026-10-06
- **Phase:** v1-gitops-core

## Context

ADR-0001 makes the pull request the platform API. A PR is only safe to merge
if the things we care about are checked before review: ownership, resource
requests, pinned images, probes, and later agent-specific limits. Reviewers
should spend their attention on *intent*, not on spotting a missing memory limit.

Checks in CI alone aren't enough: anyone with cluster access (or a
misconfigured pipeline) can bypass them. Checks at admission alone are too late,
because the author finds out after merge, when Argo CD fails to sync.

Fernhill already has 14 services that don't meet any baseline. Turning on
enforcement cluster-wide on day one would break them and make the platform team
the enemy.

## Decision

**1. Kyverno, using its CEL-based `ValidatingPolicy` API.**

**2. The same policy files are evaluated in two places:**

| Where | How | Purpose |
|---|---|---|
| CI, on every PR | `kyverno test` (policy unit tests) and, from v2, `kyverno apply` against rendered tenant manifests | Fast feedback to the author, human or agent, before review |
| Cluster admission | Kyverno admission webhook, policies synced by Argo CD | Backstop; catches anything that didn't come through a PR |

**3. Policies are code, with tests.** Each policy has passing and failing
fixtures in `platform/policies/tests/`. CI fails if a policy stops rejecting
what it should reject, or starts rejecting what it shouldn't.

**4. Enforcement is scoped by namespace opt-in, not cluster-wide.** Policies
match only namespaces labelled `platform.fernhill.io/managed=true`. Namespaces
created by the paved road (v3) get this label automatically. Existing services
come under enforcement when they migrate, which is the adoption model from the
story ("the paved road must be the easiest path, not the only path").

**5. CPU limits are deliberately not required.** Requests and memory limits
are. CPU limits cause CFS throttling under burst, with little benefit once
requests are honest. This is a common, contested choice, so the reasoning lives
in the policy file itself as well.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| OPA Gatekeeper (Rego) | Capable and more general-purpose, but Rego is a second language for a 4-person team to own, and Gatekeeper's CI story (`gator`) is less mature than `kyverno test`. If Fernhill already had Rego expertise or used OPA for non-Kubernetes authz, I'd pick it. |
| Native `ValidatingAdmissionPolicy` only | It's the upstream direction, and Kyverno's `ValidatingPolicy` uses the same CEL model, so moving over later is cheap. But VAP alone has no CI tool, no policy reports, and no mutation or generation (which v3 will need). |
| Kyverno `ClusterPolicy` (YAML pattern style) | Familiar and well documented, but it's the older API. New policies in CEL are closer to upstream and easier to port. |
| Conftest in CI only | No runtime enforcement, so it violates the "backstop" requirement. |
| Enforce cluster-wide immediately | Breaks 14 existing services on day one. Opt-in by namespace plus migration is slower but survivable. |

## Consequences

- An agent or developer that opens a non-compliant PR gets a specific CI error
  message before any human looks at it. This is what makes agent PRs cheap to
  review in v5.
- The Kyverno webhook is in the critical path for every write to managed
  namespaces. Locally it runs with one replica. In production it needs 3
  replicas, a PodDisruptionBudget, and alerting on webhook latency and errors.
- Two places to evaluate means two places that can disagree (CLI vs. in-cluster
  version skew). Mitigation: CI pins the same Kyverno version as the cluster
  (`platform/apps/values.yaml`).
- Unmanaged namespaces get no protection from these policies. That's a
  conscious trade, and their adoption is a metric worth tracking (v6).

## What would change my mind

- Policies that need data outside the object (e.g. "this team's cost budget")
  become the norm. Then a richer engine, or an external decision point, starts to earn its complexity.
- Upstream `ValidatingAdmissionPolicy` + `MutatingAdmissionPolicy` gain a solid
  offline test tool. Then dropping the Kyverno dependency for validation becomes attractive.
- Legacy namespaces are still unmigrated after two quarters. Then the opt-in model
  isn't working and we'd switch legacy namespaces to `Audit` cluster-wide, with
  reports going to the owning teams.
