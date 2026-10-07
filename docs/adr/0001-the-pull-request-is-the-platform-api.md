# ADR-0001: The pull request is the platform API

- **Status:** Accepted
- **Date:** 2026-10-06
- **Phase:** v0-foundations

## Context

Fernhill's platform has to serve two kinds of user:

1. **Developers**, who want self-service through a portal, a CLI, or plain Git.
2. **AI agents**, which engineers already use daily and which are already
   writing infrastructure code ([story, problem #3](../story.md#what-hurts-the-before-picture)).

The tempting design is to give each its own entry point: a portal backend that
calls the Kubernetes API for humans, and an agent gateway with its own
credentials and approval flow for agents. That gives you two control paths, two
audit trails, and two sets of policies that drift apart. With a team of four,
that's not something Fernhill can keep up.

There's also a compliance constraint: one customer contractually requires an
audit trail for production changes. That trail has to cover agent-authored
changes as well as human ones.

## Decision

**Every change to platform-managed state is a pull request against the GitOps
repository.** Portals, CLIs, and agents are *clients* that produce PRs. None of
them holds credentials that can write to a cluster.

```
Developer → Backstage template ─┐
                                ├→ PR → CI policy gates → human review → merge → Argo CD → admission policy → cluster
AI agent  → Platform MCP server ┘
```

Concretely:

- **Argo CD is the only writer** to platform-managed namespaces. Humans and
  agents get read-only cluster access at most.
- **The same Kyverno policies run twice**: in CI against the PR's manifests
  (fast feedback, before review) and at admission (the backstop if CI is bypassed).
- **Agents are distinguished, not separated.** Agent PRs come from a dedicated
  GitHub App identity and carry an `agent-authored` label. Agent-specific rules
  are expressed as *extra* policy on the same path. Examples: agents may only
  touch `tenants/**`, and their resource ceilings are lower. They don't get a
  different path.
- **Merge requires a human** (branch protection + CODEOWNERS). Agents can
  propose; they cannot approve.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Portal writes directly to the Kubernetes API (Backstage → kubectl apply) | Fast to demo, but no review, no history, and drift from Git. It also creates a second write path we'd have to secure. |
| Separate agent gateway with its own approval workflow | Duplicates review, audit, and policy. Agent rules would drift from human rules. Four people can't run two platforms. |
| Agents act directly with scoped ServiceAccounts + admission policy only | Admission is a backstop, not a review. Nobody looks at a change before it lands, and the audit trail lives in API server logs, not where engineers work. |
| Ticket-based (agent files a ticket, human executes) | This is the five-day database problem with extra steps. |

## Consequences

**Easier**
- One audit trail: `git log` + PR history, already familiar to auditors and engineers.
- One policy set, evaluated in two places.
- Adding a new kind of client (a CLI, a Slack bot, a different agent) is just
  another thing that opens PRs.
- Rollback is `git revert`.

**Harder**
- **Latency.** Self-service is bounded by CI time + review time + Argo sync.
  Target: under an hour end to end, and most of that is waiting for review. That
  is acceptable for infrastructure; it would not be for, say, feature flags.
- **Review load.** If agents generate lots of PRs, humans become the bottleneck.
  Mitigation: CI does the mechanical review (policy, schema, cost) so humans
  review *intent*. If that isn't enough, auto-merge for a narrow class of
  low-risk changes is the next lever, gated by policy, not by trust.
- **Git as a database.** Fine at Fernhill's scale (14 services). Revisit when
  `tenants/` holds thousands of objects or when Argo CD repo-server becomes the bottleneck.

## What would change my mind

- Review latency becomes the dominant complaint and policy-gated auto-merge
  doesn't fix it.
- Agents need to do operational actions that aren't naturally declarative
  (restart a pod, scale for an incident). Those belong behind a separate, audited
  runbook-execution path, not in Git. That would be a new ADR, not a reversal of this one.
- Fernhill grows to the point where a single GitOps repo is a contention point
  (see [ADR-0002](0002-single-repository.md)).
