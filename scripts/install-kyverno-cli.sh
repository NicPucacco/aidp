#!/usr/bin/env bash
# Installs the Kyverno CLI at the same version as the Kyverno chart pinned in
# platform/apps/values.yaml, so CI and the cluster evaluate policies identically.
set -euo pipefail

chart_version=$(awk '/^ *kyverno:/ {print $2}' platform/apps/values.yaml)
helm repo add kyverno https://kyverno.github.io/kyverno/ >/dev/null
app_version=$(helm show chart kyverno/kyverno --version "$chart_version" | awk '/^appVersion:/ {print $2}')

echo "Kyverno chart ${chart_version} -> CLI ${app_version}"
url="https://github.com/kyverno/kyverno/releases/download/${app_version}/kyverno-cli_${app_version}_linux_x86_64.tar.gz"
curl -fsSL "$url" | tar -xz -C /usr/local/bin kyverno
kyverno version
