#!/usr/bin/env bash
# End-to-end check of the portal: Backstage is up behind the Gateway, and its
# catalog has been populated from Git by git-sync: teams, the tenant's
# service, and both golden-path templates.
set -euo pipefail

CONTEXT_ARGS=()
[[ -n "${KUBE_CONTEXT:-}" ]] && CONTEXT_ARGS=(--context "$KUBE_CONTEXT")
k() { kubectl "${CONTEXT_ARGS[@]}" "$@"; }

k -n backstage rollout status deploy/backstage --timeout=10m

svc=$(k -n envoy-gateway-system get svc -l gateway.envoyproxy.io/owning-gateway-name=platform -o name)
k -n envoy-gateway-system port-forward "$svc" 18001:80 >/dev/null 2>&1 &
pf=$!
trap 'kill $pf 2>/dev/null || true' EXIT

api() { curl -fsS -H 'Host: backstage.localhost' -H "Authorization: Bearer ${token:-}" "http://127.0.0.1:18001$1"; }

for _ in $(seq 1 30); do
  token=$(curl -fsS -H 'Host: backstage.localhost' -H 'X-Requested-With: XMLHttpRequest' \
    'http://127.0.0.1:18001/api/auth/guest/refresh' 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["backstageIdentity"]["token"])' 2>/dev/null) && break
  sleep 2
done
[[ -n "${token:-}" ]] || { echo "Couldn't sign in as guest" >&2; exit 1; }

# The catalog processes locations asynchronously; give it a few minutes.
want=(component:invoice-api component:developer-portal group:billing template:new-webservice template:new-database api:webservice-api)
for _ in $(seq 1 40); do
  have=$(api '/api/catalog/entities?fields=kind,metadata.name' \
    | python3 -c 'import json,sys; print(" ".join(sorted(e["kind"].lower() + ":" + e["metadata"]["name"] for e in json.load(sys.stdin))))' 2>/dev/null || true)
  missing=()
  for w in "${want[@]}"; do [[ " $have " == *" $w "* ]] || missing+=("$w"); done
  (( ${#missing[@]} == 0 )) && break
  sleep 6
done
if (( ${#missing[@]} )); then
  echo "Catalog is missing: ${missing[*]}" >&2
  echo "Catalog has: ${have}" >&2
  exit 1
fi
echo "✓ Portal catalog populated from Git: ${want[*]}"
