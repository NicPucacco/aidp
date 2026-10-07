# Roadmap

Each phase is a git tag. Check out a tag to see the platform as it was at that
point, and read the phase notes to see *why* it moved the way it did.

| Tag | Phase | Fernhill problem it moves | Status |
|---|---|---|---|
| `v0-foundations` | Story, ADRs, repo layout, Terraform bootstrap, CI skeleton | — (groundwork) | 🚧 in progress |
| `v1-gitops-core` | Argo CD app-of-apps, Crossplane, Kyverno baseline, Gateway API | #2 one paved road | ⏳ planned |
| `v2-database-path` | `Database` API (Crossplane XRD + Python composition function → CloudNativePG) | #1 five-day databases | ⏳ planned |
| `v3-service-path` | `Service` API, shared Helm chart, ApplicationSet over `tenants/*`, DB binding | #2 one paved road | ⏳ planned |
| `v4-portal` | Backstage catalog + golden-path templates; image built in GitHub Actions | #1, #2 (discoverability) | ⏳ planned |
| `v5-agentic` | Python MCP server, PR-only GitHub App identity, agent-specific policy | #3 agents as accountable users | ⏳ planned |
| `v6-proof` | A real agent-authored PR merged in this repo, demo recording, success metrics | all three | ⏳ planned |

## Sequencing rationale

- **Paved road before portal.** The portal (v4) is a UI over APIs that already
  work from Git (v2, v3). Building Backstage first is the most common way IDPs
  fail: a beautiful catalog in front of a ticket queue.
- **Database before service.** It's the most painful ticket at Fernhill
  (5-day lead time) and the cleanest Crossplane example, so it proves the model
  with the least surface area.
- **Agents last, on purpose.** The agentic layer (v5) is deliberately thin. If
  the PR-based contract from v1–v4 is sound, agents need a new *interface*, not
  a new *platform*. See [ADR-0001](adr/0001-the-pull-request-is-the-platform-api.md).

## Explicitly out of scope

- **Multi-cluster / fleet management.** Real, but orthogonal to the story.
- **Production cloud compositions.** An AWS RDS composition is sketched to show
  the abstraction holds, but only the local composition is exercised.
- **Secrets management beyond Kubernetes Secrets.** In production this would be
  External Secrets Operator + a vault; called out in the relevant ADR.
