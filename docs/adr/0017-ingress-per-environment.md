# ADR-0017: One Gateway definition; the environment supplies domain, IP and TLS

- **Status:** Accepted
- **Date:** 2026-10-08
- **Phase:** infra (after ADR-0016)

## Context

The platform's Gateway was a `ClusterIP` service on `*.localhost` (ADR-0004),
which is right for kind and useless on AKS (ADR-0016). Production needs a
public IP, a real domain, and TLS. Several things have to agree on those
values: the Gateway, the WebService composition (tenant hostnames and status
URLs), Backstage's base URL, cert-manager, and DNS. Two failure modes to avoid:

- **Forking `platform/`** into local and AKS variants, which drift apart.
- **Hand-copying values** (an IP, a client ID) from Terraform output into
  Git, where they go stale and leak environment details into the repo.

## Decision

**1. One `environment` object, produced by Terraform, consumed by everything.**
`platform/apps/values.yaml` declares it with local defaults. On AKS,
`terraform/aks` outputs the same shape (`platform_environment`, shape-tested),
and `make platform-aks` passes it through `terraform/argocd` into the root
app. No environment-specific value is committed to Git.

| Consumer | Gets |
|---|---|
| `platform/gateway` (now a chart) | Service type, static IP, TLS listener, issuer, wildcard certificate |
| WebService composition | Base domain, scheme, port, via a Crossplane `EnvironmentConfig` read by `function-environment-configs` |
| Backstage | Its base URL |
| cert-manager (deployed only with TLS) | The workload identity it runs as |

**2. Terraform owns the edge, not the cluster.** A static Standard public IP,
the Azure DNS zone, and a wildcard **alias** record pointing at the IP
resource all live in `terraform/aks`. DNS is correct before the cluster
exists, survives a cluster rebuild, and can't drift from the address. No
ExternalDNS is needed.

**3. One wildcard certificate.** Let's Encrypt, DNS-01 via Azure DNS (wildcards
require DNS-01), with cert-manager authenticating through workload identity.
That identity is federated to `system:serviceaccount:cert-manager:cert-manager`
only, and holds DNS Zone Contributor on this zone only.

**4. Single-label tenant hostnames:** `<service>-<team>.<baseDomain>`.
A wildcard certificate covers exactly one label, so the old
`<service>.<team>.<domain>` would have needed a certificate per team. Locally
this is `invoice-api-billing.localhost`.

**5. HTTP only redirects.** With TLS on, the HTTP listener only accepts the
redirect route from the Gateway's own namespace. Tenant routes can't attach
to plain HTTP even by accident.

**6. Azure load balancer probes are TCP.** Azure probes HTTP ports with
`GET /` by default, and what Envoy answers there isn't something to depend
on. A TCP probe checks the listener is up.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| Separate local and AKS overlays (Kustomize) of `platform/` | Two trees to keep in sync. Values are the actual difference, so values are what vary. |
| ExternalDNS managing records from Routes | One more controller with write access to DNS, to manage a single wildcard record that never changes. |
| Application Gateway for Containers / AGIC | A strong Azure-native option, but it couples the platform's ingress to Azure and to a second Gateway implementation. Envoy Gateway already runs everywhere this platform does. |
| HTTP-01 per-host certificates | No wildcards, a certificate per new service, and issuance waits on DNS and routing. |
| `<service>.<team>.<domain>` with per-team wildcard certs | Needs the Gateway to know the team list and a listener per team. Single-label names are simpler for the same isolation. |

## Consequences

- `make up` (kind) is unchanged: no cert-manager, `ClusterIP`, `*.localhost`.
  CI keeps proving the local path; `terraform test` and `helm template`
  checks cover the AKS shape. Nothing has been applied to real Azure yet.
- **Tenant URLs changed** (`invoice-api.billing.localhost` →
  `invoice-api-billing.localhost`). Nothing outside this repo depended on them.
- **DNS delegation is manual, once.** Point the parent zone's NS records at the
  `name_servers` output.
- DNS Zone Contributor is broader than cert-manager needs (TXT records only).
  A custom role is the tighter follow-up.
- Client source IPs are not preserved (`externalTrafficPolicy: Cluster`). Fine
  until a tenant needs them; then switch to `Local` and verify the Cilium
  health-check node port behind Azure's probes.
- Argo CD and Backstage are now reachable on the internet (behind TLS) but
  still use local admin and guest auth. **Entra SSO is the next priority**
  (ADR-0016's follow-ups) before tenants are onboarded.

## What would change my mind

- Several clusters or regions behind one domain. Then a global front end
  (Azure Front Door) plus per-cluster Gateways, and ExternalDNS or Front
  Door origins become worth their complexity.
- Tenants needing custom domains. Then per-host certificates via cert-manager's
  Gateway API integration, alongside the wildcard.
