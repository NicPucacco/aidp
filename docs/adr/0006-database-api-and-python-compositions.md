# ADR-0006: A t-shirt-sized Database API, composed in tested Python

- **Status:** Accepted. §3 superseded by [ADR-0014](0014-compositions-are-go-templates.md) (compositions are now Go templates)
- **Date:** 2026-10-06
- **Phase:** v2-database-path

## Context

A database at Fernhill takes five working days: a ticket, hand-written
Terraform, a reviewer when one is free, and credentials pasted into a namespace
([story, problem #1](../story.md#what-hurts-the-before-picture)). Teams work
around it by running Postgres in sidecars, which is how Billing lost a day of invoices.

The platform needs a self-service database that is:

- **Small to ask for.** A team should describe what they need, not how to run it.
- **Safe by default.** HA, resource limits, and pinned versions are not the
  tenant's job to remember.
- **Portable.** The same request has to work locally (CloudNativePG) and on a
  cloud (RDS/Cloud SQL), per [ADR-0004](0004-kubernetes-agnostic-local-first.md).
- **Changeable by the platform team** without editing every tenant's YAML.

## Decision

### 1. The API is intent, not infrastructure

```yaml
apiVersion: platform.fernhill.io/v1alpha1
kind: Database
metadata:
  name: invoice-api
spec:
  size: small          # small | medium | large
  databaseName: invoices
  # version: "18"      # optional, defaults to the latest supported
```

The API has no instance counts, storage classes, or CPU numbers. What `small` means is
a table in `compose.py`, owned by the platform team. Changing it is one reviewed
PR that applies to every small database. A cloud composition maps the same
sizes to instance classes.

The API returns `status.connectionSecret`, `host`, and `port`. That's the contract the
Service API (v3) binds to.

### 2. Crossplane v2, composing Kubernetes resources directly

Crossplane v2's namespaced XRs compose ordinary Kubernetes objects (here a
CloudNativePG `Cluster`) without `provider-kubernetes`. Crossplane gets RBAC for
exactly those kinds through an aggregated ClusterRole (`platform/apis/rbac.yaml`).

### 3. Composition logic in Python, with unit tests, embedded at build time

> **Superseded by ADR-0014.** Kept for the record; the current implementation
> is a `function-go-templating` Composition tested with `crossplane render`.

The logic lives in `platform/apis/database/compose.py` and runs on
[function-python](https://github.com/crossplane-contrib/function-python).
`scripts/gen-compositions.py` embeds it into `composition.yaml`. CI:

- runs pytest against the **same SDK version** function-python ships;
- fails if `composition.yaml` is stale relative to `compose.py`;
- deploys it to a real cluster and connects to the resulting database with the
  credentials the API hands back.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Patch-and-transform (classic Crossplane) | Size → instances/storage/resources mappings become pages of patches. Hard to read and impossible to unit-test. |
| function-go-templating / KCL | Fine tools, but a templating language is a new skill for the team, and logic like readiness checks gets awkward. Python is already Fernhill's scripting language. |
| A packaged Python function (own image, own xpkg) | The right end state, but it needs an image pipeline, a registry, and package versioning before there's a second API to justify it. The generator keeps the source testable today, and moving to a packaged function later only changes the delivery, not the code. |
| Inline script edited directly in the Composition | Untestable, and a YAML block scalar is a terrible code editor. |
| Expose CloudNativePG `Cluster` directly to tenants | Couples every tenant to one operator's schema. The cloud story ends there, and so does the platform team's ability to change defaults. |
| Terraform modules triggered from CI | No continuous reconciliation, so drift goes unnoticed, and no status API to bind to. The stronger reason, that `plan` runs author-controlled code with credentials, became decisive with agent authors in v5: see [ADR-0015](0015-why-not-terraform-modules.md). |

## Consequences

- A database request is now a ~10-line file in a PR. Lead time is CI + review
  + roughly 1–2 minutes to provision locally.
- Tenants can't tune Postgres. That's deliberate for the paved road. A team with
  a real need gets a new size or field, added via a PR to the platform, so the
  need becomes visible and reusable.
- The platform team now owns a schema (`v1alpha1`). Breaking changes need a new
  version and a migration path. Crossplane XRDs support multiple served
  versions, but we have to actually use that discipline.
- `compose.py` runs inside function-python's interpreter, so it can only import
  the standard library and the Crossplane SDK. That constraint is acceptable now,
  and it's the trigger for packaging our own function.
- Backups aren't configured locally. A production composition would add a
  CloudNativePG `ScheduledBackup` to object storage, or rely on RDS automated
  backups. That's tracked as a follow-up, not hidden.

## What would change my mind

- **A second or third API needs shared helpers** (naming, labels, readiness).
  Then package our own function so modules can import each other, instead of
  copying code between embedded scripts.
- **Tenants keep asking for knobs** the sizes don't cover. Then the abstraction
  is at the wrong level. Look at what they're asking for before adding fields one by one.
- **The organisation standardises on one cloud.** Then consider whether the
  local composition is worth maintaining, or whether a cheap cloud sandbox
  replaces it.
