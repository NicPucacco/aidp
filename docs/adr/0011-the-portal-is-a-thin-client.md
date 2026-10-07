# ADR-0011: The portal is a thin client over Git

- **Status:** Accepted
- **Date:** 2026-10-07
- **Phase:** v4-portal

## Context

By v3, Fernhill teams can get a database or a service with a ~10-line PR. That
works for engineers who know the repo, and it's invisible to everyone else.
The portal's job is **discoverability**: what golden paths exist, what each
team owns, what's running, and how to ask for something new.

The most common way IDPs fail is building the portal first: a polished catalog
in front of a ticket queue. This platform deliberately built the APIs first
(v1–v3), so the portal can be thin.

## Decision

**1. Backstage, and it writes nothing but pull requests.** Golden-path
templates (`golden-paths/`) generate tenant files and open a PR with
`publish:github:pull-request`. The PR then goes through the same CI gate as
any other tenant change (ADR-0009). Backstage's Kubernetes access is a
read-only ClusterRole, so it can show what's running and can't change it
(ADR-0001).

**2. The catalog is read from Git, not registered by hand.** A `git-sync`
sidecar keeps `/repo/aidp` at the revision Argo CD tracks. Backstage reads
`catalog/*.yaml`, `tenants/*/*/catalog-info.yaml`, and
`golden-paths/*/template.yaml` as file locations. A merged PR shows up in the
catalog within about a minute, and browsing needs no GitHub token. A token is
only needed to *open* PRs (`make portal-token`).

**3. The platform dogfoods its own APIs.** Backstage's Postgres is a
`Database` (with `pluginDivisionMode: schema`, because the CloudNativePG app
user can't create databases). Its namespace is labelled `managed=true`, so the
portal meets the same baseline policies as every tenant.

**4. A custom Backstage app, built in CI, tagged by content.** The app is the
standard `@backstage/create-app` output with Fernhill config and copy. The
image tag is the **git tree hash of `portal/`**:

- CI fails if `platform/backstage/values.yaml` doesn't pin the current hash.
- PR CI builds the image and loads it into the e2e cluster (it isn't published yet).
- A merge to `main` publishes exactly that tag to GHCR.

So any commit or phase tag knows exactly which portal image it runs, with no
`:latest` and no bot commits bumping tags.

**5. Templates are tested like code.** `scripts/test-templates.py` renders every
skeleton (with and without optional parts) and runs the result through the
tenant gate. A golden path can't generate a PR that fails CI.

## Alternatives considered

| Option | Why not (here, now) |
|---|---|
| A Backstage distribution (e.g. RHDH community image + dynamic plugins) | Probably the right call for a 4-person team in production: no Node build to own. Not chosen here because this repo exists to show the build, and because Fernhill has no plugins yet that would justify either. Revisit at the first custom plugin. |
| Port / Cortex (SaaS portals) | Good products. Also a vendor dependency for the platform's front door, and they don't run locally. |
| Backstage scaffolder writes to the cluster (kubectl/Kubernetes actions) | Breaks ADR-0001: a second write path with no review. |
| GitHub discovery provider for the catalog | Needs a token just to browse, and API rate limits. git-sync is a single, boring dependency. |
| Image tag `:main` / `:latest`, or a bot that bumps tags | Floating tags break "check out a tag and get that platform". Bot commits add noise and a write-capable token. |
| Templates in `portal/` | Would change the image hash on every template edit, even though templates are read from Git at runtime. |

## Consequences

- The portal is replaceable: everything it shows lives in Git, and everything
  it does is a PR. Swapping Backstage for something else touches `portal/` and
  `platform/backstage/`, not the platform.
- Owning a Node/TypeScript build is a real cost: Backstage releases monthly,
  and upstream breakage happens. `@yarnpkg/core@4.9.2` shipped with an
  unresolvable dependency during this phase and had to be pinned.
- Local guest auth means anyone who can reach the portal can open PRs
  *as the token's owner*. In production that's SSO plus per-user GitHub
  identity, so PRs are attributed to the person who clicked. That matters for
  the audit trail (story, compliance constraint).
- **Startup ordering matters.** CloudNativePG publishes the connection Secret
  *before* Postgres accepts connections. Backstage started in that gap failed
  every plugin, but its liveness endpoint stayed 200, so it sat not-ready
  forever and was never restarted. The fix is a wait-for-db init container,
  plus a `startupProbe` on the readiness endpoint as a general backstop. Any
  `WebService` bound to a fresh `Database` faces the same race; a startup
  probe is a candidate default for the WebService composition.
- Backstage can't resolve `$text` placeholders relative to *file* locations,
  so the API entities embed their XRD schema instead. It's generated into
  `catalog/apis.yaml` by the same generator and drift check as the compositions.
- The first image publish creates a **private** GHCR package. It has to be made
  public once (a manual step) so people without credentials can pull it.

## What would change my mind

- The first custom plugin. If Fernhill needs one, the build is already here.
  If two years pass without one, switch to a distribution and delete `portal/`.
- Catalog size or freshness needs outgrow git-sync, e.g. thousands of
  entities across many repos. Then use proper discovery providers.
- Templates start needing logic that's hard to test with the Jinja2 stand-in.
  Then run Backstage's own scaffolder in CI (dry-run API).
