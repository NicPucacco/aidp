# Roadmap

Each phase is a git tag. Check out a tag to see the platform as it was at that
point. From v1, each phase lands as a pull request, and the PR description is
the phase write-up: what changed, what broke along the way, and why. The
platform's own changes go through the same contract it offers everyone else.

| Tag | Phase | Fernhill problem it moves | Status |
|---|---|---|---|
| `v0-foundations` | Story, ADRs, repo layout, Terraform bootstrap, CI skeleton | — (groundwork) | ✅ done |
| `v1-gitops-core` | Argo CD app-of-apps, Crossplane, Kyverno baseline, Gateway API | #2 one paved road | ✅ done |
| `v2-database-path` | `Database` API (Crossplane XRD + tested Python composition → CloudNativePG), tenant ApplicationSet + boundary | #1 five-day databases | 🚧 in review |
| `v3-service-path` | `Service` API, Gateway route, binding a service to its `Database` | #2 one paved road | ⏳ planned |
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

### Changes to the plan

- **v2 pulled the tenant ApplicationSet forward from v3.** A database nobody
  can request through Git doesn't prove anything, and the tenant boundary
  ([ADR-0007](adr/0007-tenant-boundary.md)) needed deciding before the first
  tenant existed, not after.

## Explicitly out of scope

- **Multi-cluster / fleet management.** Real, but orthogonal to the story.
- **Production cloud compositions.** An AWS RDS composition is sketched to show
  the abstraction holds, but only the local composition is exercised.
- **Secrets management beyond Kubernetes Secrets.** In production this would be
  External Secrets Operator + a vault; called out in the relevant ADR.
