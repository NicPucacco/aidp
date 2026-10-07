#!/usr/bin/env bash
# Waits until every Argo CD Application is Synced and Healthy.
set -euo pipefail

CONTEXT_ARGS=()
[[ -n "${KUBE_CONTEXT:-}" ]] && CONTEXT_ARGS=(--context "$KUBE_CONTEXT")
TIMEOUT_SECONDS=${TIMEOUT_SECONDS:-900}

k() { kubectl "${CONTEXT_ARGS[@]}" -n argocd "$@"; }

deadline=$((SECONDS + TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  # name sync health, one line per app
  status=$(k get applications -o jsonpath='{range .items[*]}{.metadata.name} {.status.sync.status} {.status.health.status}{"\n"}{end}' 2>/dev/null || true)
  total=$(grep -c . <<<"$status" || true)
  ready=$(grep -c ' Synced Healthy$' <<<"$status" || true)

  # The root app alone means the children haven't been created yet.
  if (( total > 1 && ready == total )); then
    echo "All ${total} applications Synced/Healthy."
    echo "$status" | column -t
    exit 0
  fi
  echo "[$(date +%T)] ${ready}/${total} applications ready"
  sleep 15
done

echo "Timed out waiting for applications:" >&2
echo "$status" | column -t >&2
exit 1
