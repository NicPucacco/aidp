#!/usr/bin/env bash
# End-to-end proof of the Database golden path: the Database declared in
# tenants/billing/invoice-api becomes a Postgres that accepts connections
# using only the credentials the platform hands back.
set -euo pipefail

CONTEXT_ARGS=()
[[ -n "${KUBE_CONTEXT:-}" ]] && CONTEXT_ARGS=(--context "$KUBE_CONTEXT")
k() { kubectl "${CONTEXT_ARGS[@]}" -n billing "$@"; }

echo "Waiting for Database billing/invoice-api to be Ready..."
k wait database/invoice-api --for=condition=Ready --timeout=10m

secret=$(k get database/invoice-api -o jsonpath='{.status.connectionSecret}')
echo "Connection secret: ${secret}"
uri=$(k get secret "$secret" -o jsonpath='{.data.uri}' | base64 -d)

primary=$(k get pods -l cnpg.io/cluster=invoice-api,cnpg.io/instanceRole=primary -o name)
result=$(k exec "$primary" -c postgres -- psql "$uri" -tAc 'select current_database()')
if [[ "$result" != "invoices" ]]; then
  echo "Expected database 'invoices', got '${result}'" >&2
  exit 1
fi
echo "✓ Connected to '${result}' with the platform-issued credentials"
