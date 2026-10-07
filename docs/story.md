# Fernhill Freight: the problem this platform solves

> Fernhill Freight is fictional. The problems are not — every one of them is a
> composite of things I've seen in real platform teams.

## The company

Fernhill Freight is a mid-sized logistics company. It runs route planning,
warehouse management, customer tracking, and invoicing for about 400 business
customers.

| | |
|---|---|
| Engineers | ~60, in 5 stream-aligned teams (Routing, Warehouse, Tracking, Billing, Customer Portal) |
| Platform team | 4 engineers, formed 9 months ago out of the old "Ops" team |
| Services | 14 in production, plus a long tail of cron jobs and scripts |
| Runtime | Kubernetes, but each team adopted it separately |
| Compliance | SOC 2 Type II; one large customer contractually requires change audit trails |

## What hurts (the "before" picture)

**1. A database takes five days.**
Teams file a ticket. The platform team hand-writes Terraform, someone reviews it
when they can, and credentials get pasted into the team's namespace. Median
lead time from request to usable database: **5 working days**. Teams work around
this by running Postgres in a sidecar, which is how Billing lost a day of
invoices in March.

**2. Fourteen services, fourteen ways to deploy.**
Three teams use Helm, one uses Kustomize, one uses raw manifests applied from a
laptop. Resource limits, health checks, and ownership labels are present on
roughly half of workloads. When an alert fires at 3am, on-call has to work out
*who owns this* from Slack history.

**3. Agents have arrived — without a seat at the table.**
Since early 2026 most engineers use coding agents daily. Productivity is up,
but agents are now writing Kubernetes YAML and Terraform that look plausible and
are subtly wrong: no limits, `:latest` tags, a `db.r6g.4xlarge` for a service that
handles 3 requests a minute. Nobody can tell from a diff whether a human or an
agent wrote it, and the auditors have started asking.

## What leadership asked for

The CTO gave the platform team three outcomes for the next two quarters:

1. **Self-service with guardrails.** A team can get a new service or a database
   in under an hour without filing a ticket, and it's compliant by default.
2. **One paved road.** New services ship the same way. Existing services migrate
   when they next have meaningful change, not in a big-bang rewrite.
3. **Agents as accountable users.** Agents can use the platform, but every change
   they make is attributable, reviewable, and bounded — and the platform team
   doesn't have to build a second, parallel system to make that true.

## Constraints the platform team accepted

- **4 people.** Anything that needs a dedicated operator to babysit it is out.
- **No new cloud spend to prove the idea.** The first version must run locally
  and on the existing clusters, so the abstractions can't be tied to one provider.
- **Teams keep their autonomy.** The paved road must be the *easiest* path, not
  the *only* path. Escape hatches are allowed; they just aren't free.

## How this repository answers it

Each phase on the [roadmap](roadmap.md) moves one of these problems. The reasoning
behind each decision is in the [ADRs](adr/).
