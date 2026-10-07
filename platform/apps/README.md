# platform/apps

The root Argo CD `Application` (created by `bootstrap/terraform`) syncs every
manifest under this directory. Each file here is an Argo CD `Application` for
one platform component: the app-of-apps pattern.

Empty in `v0-foundations`. Populated from `v1-gitops-core`.

Owned by the platform team (see [CODEOWNERS](../../.github/CODEOWNERS)).
