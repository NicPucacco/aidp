#!/usr/bin/env bash
# Proves the policies tested in CI are the ones enforced at admission
# (ADR-0005): the same fixtures must be accepted/rejected by the live cluster.
# Uses server-side dry-run, so nothing is actually created.
set -euo pipefail

CONTEXT_ARGS=()
[[ -n "${KUBE_CONTEXT:-}" ]] && CONTEXT_ARGS=(--context "$KUBE_CONTEXT")
k() { kubectl "${CONTEXT_ARGS[@]}" "$@"; }

fixtures=platform/policies/tests/resources
fail=0

k create namespace billing --dry-run=client -o yaml \
  | k label --local -f - platform.fernhill.io/managed=true -o yaml \
  | k apply -f - >/dev/null
k create namespace legacy --dry-run=client -o yaml | k apply -f - >/dev/null

expect() {
  local want=$1 name=$2 got out
  if out=$(k apply --dry-run=server -f "${fixtures}/${name}.yaml" 2>&1); then
    got=admit
  else
    got=deny
  fi
  if [[ "$got" == "$want" ]]; then
    printf '  \033[32m✓\033[0m %-22s %s\n' "$name" "$got"
  else
    printf '  \033[31m✗\033[0m %-22s wanted %s, got %s\n      %s\n' "$name" "$want" "$got" "$out"
    fail=1
  fi
}

echo "Admission results:"
expect admit compliant
expect deny  noncompliant
expect deny  registry-port-no-tag
expect admit legacy-app
# Agent limits (ADR-0013), on the platform's own API objects.
expect admit agent-small-database
expect deny  agent-large-database
expect deny  agent-many-replicas
expect admit human-large-database

exit "$fail"
