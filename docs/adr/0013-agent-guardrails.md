# ADR-0013: Agent guardrails are layered, and limits follow who asked

- **Status:** Accepted
- **Date:** 2026-10-07
- **Phase:** v5-agentic

## Context

ADR-0012 gives agents a tool that opens PRs. That tool is helpful, but it
isn't a control: an agent (or a person driving one) can ignore it and push
YAML directly. Fernhill also has a contractual audit requirement covering
production changes, which now has to cover agent-authored ones.

Agents differ from humans in ways that matter for risk:

- **Volume:** they can open many requests quickly.
- **Confidence:** a wrong request looks as polished as a right one.
- **Accountability:** a person can be asked "why?" next week; an agent session can't.

## Decision

### Guardrails are layered so that no single layer is trusted

| Layer | Role | Trust |
|---|---|---|
| MCP server checks | Fast, specific feedback | **None.** UX only |
| CI: agent guardrails (`scripts/check-agent-pr.py`) | Agent PRs only touch `tenants/**`, every object is stamped `requested-by: agent:<name>`, the PR has a real `## Why`, and the `agent-authored` label is present | Control, keyed on identity |
| CI: tenant gate (ADR-0009) | Renders through real compositions; runs **all** policies, including agent limits, on the XRs | Control |
| Human review (CODEOWNERS, branch protection) | Intent: should this exist at all? | Control. Agents cannot approve |
| Admission (Kyverno `agent-limits`) | Same limits, at the cluster | Backstop if CI is bypassed |

### Limits follow *who asked*, recorded on the object

Objects proposed by agents carry `platform.fernhill.io/requested-by:
agent:<name>`. The `agent-limits` policy applies only to those: at most
`medium`, at most 3 replicas. A human can still request `large`.

The annotation is what lets **admission** distinguish them. By the time
Argo CD applies an object, the PR author is gone, but the annotation persists.
CI then makes the annotation **mandatory** on agent PRs, so an agent can't
avoid the limits by leaving it off.

### Tested as attacks, not just features

`scripts/test-agent-proposals.py` writes what a **rogue** agent would push, an
agent-stamped `large` database that skipped the server's checks, and CI must
reject it. A unit test also keeps the server's fast-feedback limits in step
with the policy, so agents aren't told "fine" by the server and "no" by CI.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Same limits for everyone | Either too tight for humans (who have context and accountability) or too loose for agents. The risk differs, so the limit should. |
| Limits only in the MCP server | Bypassable by definition. |
| Limits only in CI, keyed on PR author | Doesn't survive to the cluster. An object merged via a human's PR that an agent wrote would pass admission unchecked. The annotation travels with the object. |
| Separate namespaces or clusters for agent-requested resources | Splits ownership and on-call for the same service by *who typed the request*. Teams own services; agents act on a team's behalf. |
| Cost budgets per agent | Better than size caps in principle. Needs cost data the platform doesn't have yet (v6 metrics). Size is a reasonable proxy until then. |

## Consequences

- An agent can do useful work end to end (discover, propose, iterate on CI)
  without any permission a human reviewer wouldn't sign off on.
- Audit answers "who asked?" from Git (bot author, commit trailers, PR
  label) and from the cluster (`requested-by` annotation), which is what the
  compliance requirement needs.
- **A human can launder an agent request** by removing the annotation and
  opening the PR themselves. That's acceptable: it becomes a human request,
  with a human accountable for it.
- **Agents can only create, not modify.** The server refuses existing paths.
  Modification is the next step, and needs a design for diffs that reviewers can trust.
- Agent identity in CI is matched by bot login (`AGENT_AUTHORS`), label, or
  branch prefix. Detection by label/branch is advisory; the bot identity is
  the reliable signal, which is why ADR-0012 insists on a GitHub App.

## What would change my mind

- Evidence that agent proposals are reliably good. Measure it: v6 tracks the
  agent PR acceptance rate and CI first-pass rate. Then raise the limits,
  through a PR to `agent-limits.yaml`, like any other policy change.
- Agent volume high enough that reviewers rubber-stamp. Then fewer, better
  agent PRs (batching, stricter "Why" requirements) beats more automation.
