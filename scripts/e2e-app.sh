#!/usr/bin/env bash
# End-to-end proof of the App golden path: tenants/billing/invoice-api/app.yaml
# becomes a running service, reachable through the platform Gateway, with its
# Database credentials injected.
set -euo pipefail

CONTEXT_ARGS=()
[[ -n "${KUBE_CONTEXT:-}" ]] && CONTEXT_ARGS=(--context "$KUBE_CONTEXT")
k() { kubectl "${CONTEXT_ARGS[@]}" "$@"; }

echo "Waiting for App billing/invoice-api to be Ready..."
k -n billing wait app.platform.fernhill.io/invoice-api --for=condition=Ready --timeout=10m

db=$(k -n billing exec deploy/invoice-api -- printenv PGDATABASE)
[[ "$db" == "invoices" ]] || { echo "PGDATABASE is '${db}', expected 'invoices'" >&2; exit 1; }
echo "✓ Database credentials injected (PGDATABASE=${db})"

svc=$(k -n envoy-gateway-system get svc -l gateway.envoyproxy.io/owning-gateway-name=platform -o name)
k -n envoy-gateway-system port-forward "$svc" 18000:80 >/dev/null 2>&1 &
pf=$!
trap 'kill $pf 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  body=$(curl -fsS -H 'Host: invoice-api.billing.localhost' http://127.0.0.1:18000/ 2>/dev/null) && break
  sleep 2
done
if ! grep -q 'Fernhill Billing' <<<"${body:-}"; then
  echo "Gateway route didn't return the app. Body: ${body:-<none>}" >&2
  exit 1
fi
echo "✓ http://invoice-api.billing.localhost served through the platform Gateway"
