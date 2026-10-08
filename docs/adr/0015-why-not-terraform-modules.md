# ADR-0015: Tenants submit data, not code, so the platform API isn't Terraform modules

- **Status:** Proposed
- **Date:** 2026-10-07
- **Phase:** v5-agentic

## Context

The obvious challenge to v2–v4 is: *why build Crossplane APIs when a Terraform
repo with good modules does the same job?* That's a fair question. ADR-0006
answered it in one line, and that answer was weak. Fernhill's five-day lead
time came from the ticket queue and waiting for a reviewer, not from Terraform.
Modules with policy-gated self-merge would remove most of that wait.

Terraform modules also have real advantages for agents specifically:

- **Fluency.** Models write Terraform well. There's far more of it in their
  training data than Crossplane claims.
- **Compression.** A module call is about 10 lines, the same as a `Database`
  claim. Both keep review small, and that's the property ADR-0001 relies on
  when agents increase PR volume.
- **`terraform plan`.** It diffs the change against *live* state. Our render
  gate (ADR-0009) shows what will be composed, not what will change.

So writing less isn't the argument for an API. The argument comes from v5:
**authors are now untrusted.** An agent's PR is input from a party that can be
prompt-injected, and ADR-0001 requires that it can't reach credentials before
a human has looked at it.

Running Terraform on an agent's PR breaks that rule in two ways:

1. **Plan runs author-controlled code with credentials.** An `external` data
   source, a provider the agent chose, or a module `source` that brings in
   either of those all execute during `init`/`plan`, before review, with
   whatever cloud credentials and state access the plan job has.
2. **Plan needs state, and state holds secrets.** Generated database passwords
   live in state. A plan job that can read state for the team's databases can
   read every one of those passwords.

Both can be mitigated: read-only plan roles, allow-listed module sources,
plan only after approval, per-team state. The mitigations, though, work
against how Terraform runs, and each one has to keep holding as the
repository changes.

## Decision

**A tenant change is data that platform code interprets, never code the
platform executes.** A tenant PR may contain only `platform.fernhill.io`
objects (ADR-0007). Everything that runs because of that PR is code the
platform team owns:

| Stage | What runs | Credentials |
|---|---|---|
| CI | `check-tenants.py`, `crossplane render` running our `compose.py`, `kyverno apply` | **None.** CI has no cloud or cluster credentials (ADR-0001, ADR-0009). |
| After merge | Argo CD applies the claim; Crossplane runs the composition | Held by controllers, never by the author or CI |
| Feedback | `status.conditions`, `status.connectionSecret` on the claim | Read-only, and the v5 MCP server can query it |

The last row matters more for agents than for humans. An agent that opened a
PR has to be able to ask "is my database ready, and where are its
credentials?" through an API. The answer shouldn't be in a CI log or a state
file.

Terraform stays where ADR-0003 put it: the day-0 bootstrap, run by a trusted
operator.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Terraform modules, plan on every PR (Atlantis / TFC) | Plan runs author-controlled HCL with credentials and state access before review. Fine for trusted employees with normal CI hygiene. That's the wrong default for agent authors. |
| The same, hardened: read-only plan role, allow-listed `source`s, plan after approval | Workable, but every control depends on configuration that has to keep holding. Plan-after-approval also removes the pre-review feedback ADR-0009 exists to provide. |
| Tenants commit only a `.tfvars`/JSON input; a platform-owned root module plans it on a trusted runner | **The strongest alternative.** It fixes the credential problem, but by turning the input into a data API, which is this decision implemented in Terraform. It still lacks continuous reconciliation and a status API, and it needs per-team state to contain secrets. It's the right choice for an org without Kubernetes. |
| Agents write raw IaC with no abstraction | Every change is bespoke, so review cost grows with PR volume, which is the bottleneck ADR-0001 warns about. |

## Consequences

- **The credential story fits in one sentence:** nothing an author writes
  executes, and nothing that runs before review holds credentials. That's the
  claim v5's agent policy rests on.
- **We give up `plan`'s live diff.** Render shows intended resources, not the
  change to running ones. Follow-up: render the base branch and the PR, then
  post the diff of composed resources as a PR comment.
- **Agents are less fluent here than in Terraform.** Their output is tiny and
  schema-validated, so this costs little. The MCP server should serve the XRD
  schemas so agents don't guess fields.
- **The platform team owns Crossplane.** That means compositions, function
  upgrades, and a control plane with a real footprint (v4 already hit the
  8 GB local ceiling). A Terraform shop wouldn't carry that cost.
- **Upgrades are central.** A composition change moves every claim at once
  (fast fleet-wide fixes, fleet-wide blast radius). ADR-0010's
  add → migrate → remove discipline is what makes that safe.

## What would change my mind

- **Untrusted plans become safe by default.** For example, Terraform/OpenTofu
  gains a supported mode that plans tenant input with no credentials and no
  secret-bearing state, with apply on a trusted runner. Then the credential
  argument goes away, and modules plus policy-on-plan is the simpler,
  more familiar choice.
- **Agents stop being authors.** If agents only draft changes that a human
  re-submits under their own identity, authors are trusted again, and
  Terraform modules are an equal option.
- **The platform's resources are mostly cloud, not Kubernetes.** If Fernhill
  stops running workloads on Kubernetes, keeping a cluster only to host
  Crossplane is hard to justify. The `.tfvars`-as-API alternative above becomes the choice.
- **The Crossplane control plane costs more than it saves**, in upgrades,
  footprint, or how hard it is to hire for, at Fernhill's scale of four platform engineers.
