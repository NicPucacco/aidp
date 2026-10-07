#!/usr/bin/env bash
# Content-addressed portal image (ADR-0011): the tag is the git tree hash of
# portal/, so any commit knows exactly which image it needs, and a PR that
# changes portal/ without updating platform/backstage/values.yaml fails CI.
#
#   scripts/portal-image.sh tag     print the expected tag
#   scripts/portal-image.sh check   fail if values.yaml doesn't match
#   scripts/portal-image.sh build   build locally (and kind-load if CLUSTER is set)
set -euo pipefail
cd "$(dirname "$0")/.."

repo=$(awk '/^ *repository:/ {print $2}' platform/backstage/values.yaml)
pinned=$(awk '/^ *tag:/ {gsub(/"/, "", $2); print $2}' platform/backstage/values.yaml)
# Tree hash of portal/ as committed. Uncommitted changes aren't included, so
# commit before building an image you intend to ship.
expected=$(git rev-parse HEAD:portal)

case "${1:-tag}" in
  tag)
    echo "$expected"
    ;;
  check)
    if [[ "$pinned" != "$expected" ]]; then
      echo "platform/backstage/values.yaml pins ${repo}:${pinned}" >&2
      echo "but portal/ is at tree ${expected}. Set image.tag to ${expected}." >&2
      exit 1
    fi
    echo "✓ portal image tag matches portal/ (${expected})"
    ;;
  build)
    docker build -t "${repo}:${expected}" portal
    if [[ -n "${CLUSTER:-}" ]]; then
      kind load docker-image "${repo}:${expected}" --name "$CLUSTER"
    fi
    ;;
  *)
    echo "usage: $0 tag|check|build" >&2
    exit 2
    ;;
esac
