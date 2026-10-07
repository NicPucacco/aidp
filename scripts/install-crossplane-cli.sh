#!/usr/bin/env bash
# Installs the Crossplane CLI used by scripts/check-tenants.py.
#
# Since v2.3 the CLI ships from its own repo (crossplane/cli) on a separate
# release train, so it can't be derived from the core chart version the way
# the Kyverno CLI is. Pin the CLI release closest to the core minor in
# platform/apps/values.yaml.
set -euo pipefail

VERSION=${CROSSPLANE_CLI_VERSION:-v2.4.1}
INSTALL_DIR=${INSTALL_DIR:-/usr/local/bin}

os=$(uname -s | tr '[:upper:]' '[:lower:]')
case $(uname -m) in
  x86_64 | amd64) arch=amd64 ;;
  arm64 | aarch64) arch=arm64 ;;
  *) echo "unsupported arch $(uname -m)" >&2; exit 1 ;;
esac

curl -fsSL "https://cli.crossplane.io/stable/${VERSION}/bin/${os}_${arch}/crossplane" -o "${INSTALL_DIR}/crossplane"
chmod +x "${INSTALL_DIR}/crossplane"
"${INSTALL_DIR}/crossplane" version --client
