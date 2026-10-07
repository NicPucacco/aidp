#!/usr/bin/env bash
# Checks the tools `make up` needs. Only docker, kubectl, and terraform are
# required to install onto an existing cluster; kind is only for the local default.
set -euo pipefail

missing=0
check() {
  if command -v "$1" >/dev/null 2>&1; then
    printf '  \033[32m✓\033[0m %s\n' "$1"
  else
    printf '  \033[31m✗\033[0m %s  (%s)\n' "$1" "$2"
    missing=1
  fi
}

echo "Required:"
check docker    "https://docs.docker.com/get-docker/"
check kubectl   "brew install kubectl"
check terraform "brew install hashicorp/tap/terraform"
check kind      "brew install kind  — only needed for the local default cluster"

if ! docker info >/dev/null 2>&1; then
  printf '  \033[31m✗\033[0m docker daemon is not running\n'
  missing=1
fi

exit "$missing"
