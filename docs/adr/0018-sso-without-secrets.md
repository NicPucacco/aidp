# ADR-0018: Entra ID sign-in for Argo CD and the portal, with no client secrets

- **Status:** Accepted
- **Date:** 2026-10-08
- **Phase:** infra (after ADR-0017)

## Context

ADR-0017 put Argo CD and Backstage on the internet over HTTPS. Both still
used the local auth that was fine on kind: Argo CD's built-in `admin`, and
Backstage's guest provider. Fernhill uses Microsoft Entra ID for everything
else, and has the audit requirement from the story: who did what has to be
answerable.

The usual Entra setup is an app registration with a **client secret** stored
in the cluster. That's a credential to rotate, a Kubernetes Secret to protect,
and, until Key Vault and External Secrets exist (ADR-0016), a value someone
would have to paste in by hand.

## Decision

**1. Both apps sign in with Entra ID through workload identity federation.**
Each app registration has a federated credential that trusts exactly one
ServiceAccount in this cluster:

| App | Signs users in with | Trusts |
|---|---|---|
| Argo CD | Native OIDC, `azure.useWorkloadIdentity: true` | `argocd/argocd-server` |
| Portal | oauth2-proxy (`--entra-id-federated-token-auth`) in front of Backstage | `backstage/oauth2-proxy` |

There's no client secret anywhere: not in Git, Terraform state, the cluster,
or anyone's clipboard.

**2. Who gets in is decided by Entra, then refined by the app.**
- App registrations require assignment, so Entra refuses anyone outside the
  `admins` and `engineers` groups before either app sees a request.
- Argo CD RBAC: admins → `role:admin`, engineers → `role:readonly`, everyone
  else → nothing (`policy.default: ""`). Day-to-day changes are PRs (ADR-0001),
  so read-only is the right default for engineers.
- Argo CD's local `admin` is disabled where SSO is on. Break-glass is
  `kubectl` through AKS's Entra-backed RBAC (ADR-0016).

**3. The portal is authenticated at the edge first.** oauth2-proxy sits
between the Gateway and Backstage, and the Gateway route points only at
oauth2-proxy when SSO is on. Backstage's own sign-in stays guest for now
(see Consequences).

**4. One environment object, again.** `terraform/aks` creates the app
registrations and federated credentials and adds `sso` to
`platform_environment` (ADR-0017). The same charts render locally with SSO
off, and CI renders and policy-checks both shapes (`scripts/check-charts.py`).

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Client secrets in Kubernetes Secrets | A credential to rotate and protect. Workload identity removes it entirely, and AKS already has it on (ADR-0016). |
| Dex as an SSO broker for both | A third component with its own Entra secret, to broker for two apps that can each speak to Entra directly. |
| Envoy Gateway's OIDC `SecurityPolicy` for the portal | Elegant (auth at the Gateway itself), but it requires a client secret. Worth revisiting if it gains federated-credential support. |
| Backstage's Microsoft auth provider | Gives per-user identity *inside* Backstage, but needs a client secret today and code in `portal/`. It's the next step, after secrets have a home (Key Vault). |
| Keep Argo CD `admin` as a fallback | A shared static password on an internet-facing control plane. Break-glass belongs at the cluster level. |

## Consequences

- **The portal knows a user is a Fernhill engineer, but not *which* one.**
  Backstage still signs in as guest behind oauth2-proxy, so templates open
  PRs as the portal's token rather than the person (ADR-0011). Per-user
  identity in Backstage (Microsoft provider, or the oauth2-proxy provider
  plus catalog users from Microsoft Graph) is the follow-up, and matters for
  the audit requirement.
- **oauth2-proxy runs one replica.** Its session-cookie key is generated per
  pod into memory and never stored, so a restart signs everyone out and Entra
  silently signs them back in. Scaling out needs a shared key, which belongs
  in Key Vault (ADR-0016's secrets follow-up).
- **Applying Terraform now needs Microsoft Graph permissions**
  (`Application.ReadWrite.OwnedBy`, `AppRoleAssignment.ReadWrite.All`). That's
  often a separate approval in enterprises; plan for it.
- **Tenants may require admin consent** for the apps' sign-in permissions,
  depending on Entra's user-consent policy. That's a one-time action by a
  tenant admin.
- **Nothing has been signed into yet.** The configuration is checked against
  the real Argo CD chart (rendered values land in `argocd-cm`,
  `argocd-rbac-cm`, the ServiceAccount, and the pod labels), plus Terraform
  plan tests and policy checks. A real sign-in needs the AKS environment applied.

## What would change my mind

- Envoy Gateway's OIDC filter accepting federated credentials. Then move
  edge auth into the Gateway and drop oauth2-proxy.
- More internal UIs needing the same protection (Grafana, etc.). Then a
  shared edge-auth pattern (one oauth2-proxy per host, or Gateway-level OIDC)
  becomes worth standardising.
