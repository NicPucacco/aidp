# ADR-0010: Platform APIs are added freely and removed deliberately

- **Status:** Accepted
- **Date:** 2026-10-07
- **Phase:** v3-service-path

## Context

While building v3, the `App` kind was renamed to `WebService` (ADR-0008) in one
commit: new XRD added, old XRD removed, tenant file switched. Argo CD then
pruned the old XRD and the last `App` in the same sync, and the platform
**deadlocked**:

1. Deleting the `apps` XRD stopped Crossplane's controller for `App` objects.
2. The remaining `App` still carried Crossplane's finalizer, which only that
   controller removes, so it could never finish deleting.
3. Its Deployment (owned by the stuck `App`) blocked the new `WebService`
   from composing a Deployment with the same name.

It took manual finalizer surgery to recover. On a `Database` the same sequence
would strand every team's database, and with the wrong recovery, delete it.

## Decision

**1. XRDs are never pruned or cascade-deleted by Argo CD.** Every XRD carries
`argocd.argoproj.io/sync-options: Prune=false,Delete=false`. Removing an XRD
from Git leaves it running and marks the app OutOfSync. That's a visible,
deliberate signal, not an accident.

**2. Breaking changes follow add → migrate → remove, across separate PRs:**

| Step | Change | Done when |
|---|---|---|
| Add | New XRD (or new version on the existing XRD) served alongside the old | Both kinds work |
| Migrate | Tenant files move to the new kind/version, a team at a time | `kubectl get <old> -A` is empty |
| Remove | Delete the old XRD from Git *and* manually from the cluster | Platform team does it, with the check above in the PR |

**3. Prefer versions over renames.** Within a kind, add `v1beta1` next to
`v1alpha1` on the same XRD (Crossplane serves multiple versions). Rename a kind
only when its name is wrong, as it was here.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Let Argo CD prune XRDs, and be careful | "Be careful" isn't a control. The failure is easy to trigger and expensive to recover from. |
| Sync waves so XRs are pruned before XRDs | Ordering helps on the happy path, but the XR's deletion still depends on the controller that the XRD deletion stops. It also doesn't protect against deleting the Argo CD app. |
| Kyverno policy blocking XRD deletion while instances exist | A good extra layer for a larger team. Here the annotation removes the failure mode at its source with no new moving parts. |

## Consequences

- Removing an API is a manual, platform-team-only action. That's intended
  friction for the most destructive operation the platform has.
- The `apis` Argo CD app can show OutOfSync during a migration window. That's
  expected and should be read as "migration in progress".
- CI's e2e builds a fresh cluster, so it never exercises migrations. Upgrade
  testing (bootstrap at the previous tag, then sync to the PR) is the
  follow-up that would have caught this automatically.

## What would change my mind

- Crossplane gains safe XRD deletion semantics, e.g. refusing to delete an XRD
  with live XRs. Then the annotation becomes redundant.
- API changes become frequent enough that the manual removal step is a
  bottleneck. That would be its own warning sign about API design.
