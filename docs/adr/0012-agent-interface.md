# ADR-0012: Agents get an MCP server that can only open pull requests

- **Status:** Accepted
- **Date:** 2026-10-07
- **Phase:** v5-agentic

## Context

Fernhill engineers already use coding agents daily, and those agents are
already writing infrastructure YAML that nobody can attribute
([story, problem #3](../story.md#what-hurts-the-before-picture)). The goal is
not to stop that, but to give agents a **paved road** that is easier than
writing raw YAML, and that keeps every change attributable, reviewable, and
bounded.

v1–v4 built a platform whose only write path is a pull request (ADR-0001), with
golden paths, a CI gate that checks intent-level config (ADR-0009), and a
portal that is just another PR client (ADR-0011). The question for v5 is what
interface an agent should get.

## Decision

**A small Python MCP server (`agents/platform-mcp`) that reads the repo and
whose only write is "open a pull request".**

1. **Discovery tools read Git**, the same files Backstage and Argo CD read:
   teams, catalog, golden paths, and API schemas straight from the XRDs.
   There is no agent-specific data model to drift.
2. **Proposals render the same golden-path skeletons as Backstage**
   (`golden-paths/`). An agent's new service is byte-for-byte what a human
   clicking through the portal would get, plus one annotation recording that
   an agent asked (ADR-0013).
3. **Validate before writing.** Proposals are checked against the XRD schema
   and the agent limits, and returned with specific problems. Tools default to
   **dry run**, so exploring is free.
4. **Write = one PR, as the agent's own identity.** A GitHub App
   (`aidp-agent[bot]`) with contents/pull-requests/issues write and checks read, on one repo.
   Branches are `agent/<team>/<name>`, the PR is labelled `agent-authored`, the
   commit carries `Agent:` and `Requested-via:` trailers, and the PR body leads
   with **Why**.
5. **Agents can watch their own PR** (`get_proposal_status`) and iterate on CI
   failures, which works because ADR-0009 makes CI failures specific.
6. **Shipped with the repo** (`.mcp.json`), so any MCP client opened in this
   repo gets the platform tools.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Backstage's MCP actions backend (ships in 1.55) | Real option. But scaffolder actions run with **the portal's** GitHub identity, so agent PRs would look like portal PRs, losing exactly the attribution problem #3 is about. It also makes every agent depend on the portal being up. A good fit later for *read* tools (catalog search) once the portal has real auth. |
| Agents write raw YAML; CI catches problems | That's the status quo. Agents are fluent in Kubernetes YAML, so they produce plausible, wrong config, and reviewers can't tell a careful change from a confident guess. |
| Give agents a ServiceAccount / kubectl | Contradicts ADR-0001: a second write path with no review and no Git history. |
| A bespoke agent gateway with its own approval queue | Rebuilds PR review, audit, and policy, worse. Four people can't run two platforms. |
| TypeScript MCP server (match Backstage) | Python matches the rest of the platform code (compositions, scripts, tests), and Jinja2 renders the Nunjucks skeletons for the subset we use. |

## Consequences

- **The IDP → ADP step is small**, which is the point. v5 added an interface
  (~580 lines of Python, including docstrings), a policy, and a CI job. It didn't add a new control plane, a new
  approval flow, or new cluster permissions.
- **One definition of "a new service".** The skeletons are rendered by
  Backstage, by `scripts/test-templates.py`, and by the MCP server; CI tests
  the latter two through the tenant gate.
- **Agent capabilities track golden paths.** A new golden path needs a new
  `propose_*` tool. That's deliberate: agents get the paved road, not raw Kubernetes.
- **GitHub App setup is manual** (documented in `docs/agents.md`). Without it,
  the server runs in dry-run mode or with a personal token, which weakens
  attribution.
- The server reads a local checkout, so it proposes against whatever the agent
  has checked out. CI checks against the PR's base, so a stale checkout fails
  loudly rather than silently.

## What would change my mind

- Backstage's MCP actions gain per-user (or per-agent) identity for
  scaffolder runs. Then its templates would be the single proposal engine,
  and this server would shrink to the read tools, or disappear.
- Agents need operational actions (restart, scale for an incident). Those
  aren't declarative and don't belong in Git. They'd need a separate, audited
  runbook path, which deserves its own ADR.
- Agent PR volume swamps reviewers. Then the next lever is policy-gated
  auto-merge for a narrow class of changes (ADR-0001), not more agent permissions.
