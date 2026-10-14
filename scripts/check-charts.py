#!/usr/bin/env python3
"""Render the platform's own charts for every environment and hold their
workloads to the same baseline policies as tenants (ADR-0005).

CI's e2e only exercises the local (kind) environment. This makes sure the
AKS shape (TLS, LoadBalancer, SSO) renders too, and that anything the
platform deploys into a policy-managed namespace (e.g. the portal and its
oauth2-proxy) would be admitted.

Usage: scripts/check-charts.py   (needs helm and the kyverno CLI)
"""

import pathlib
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
AKS = ROOT / "scripts" / "fixtures" / "environment-aks.values.yaml"
POLICIES = sorted(str(p) for p in (ROOT / "platform" / "policies").glob("*.yaml"))
GROUP = "platform.fernhill.io"


def api_fields() -> dict[str, set[str]]:
    """Top-level spec fields each platform API accepts, from its XRD."""
    fields = {}
    for definition in (ROOT / "platform" / "apis").glob("*/definition.yaml"):
        xrd = yaml.safe_load(definition.read_text())
        spec = xrd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["spec"]
        fields[xrd["spec"]["names"]["kind"]] = set(spec.get("properties", {}))
    return fields


def unknown_fields(rendered: dict[str, list[dict]]) -> list[str]:
    """Platform API objects using fields their XRD doesn't define. The API
    server would silently drop them, and Argo CD would show the app
    OutOfSync forever (this is how a removed `size` field surfaced)."""
    allowed, problems = api_fields(), []
    for chart, docs in rendered.items():
        for d in docs:
            if d.get("apiVersion", "").startswith(GROUP) and d["kind"] in allowed:
                extra = set(d.get("spec") or {}) - allowed[d["kind"]]
                if extra:
                    problems.append(f"{chart}: {d['kind']} {d['metadata']['name']} sets unknown field(s) {sorted(extra)}")
    return problems
MANAGED_NAMESPACES = ["backstage"]  # labelled platform.fernhill.io/managed=true by its chart


def helm(chart: str, *args: str) -> list[dict]:
    out = subprocess.run(["helm", "template", chart, str(ROOT / "platform" / chart), *args],
                         check=True, capture_output=True, text=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


def portal_values(environment: str) -> list[str]:
    """The values platform/apps would pass to the portal chart."""
    apps_args = ["-f", str(AKS)] if environment == "aks" else []
    app = next(d for d in helm("apps", *apps_args) if d["kind"] == "Application" and d["metadata"]["name"] == "backstage")
    values = app["spec"]["source"]["helm"]["valuesObject"]
    tmp = pathlib.Path(tempfile.mkdtemp()) / "values.yaml"
    tmp.write_text(yaml.safe_dump(values))
    return ["-f", str(tmp)]


def main() -> int:
    failures = 0
    for environment in ("local", "aks"):
        env_args = ["-f", str(AKS)] if environment == "aks" else []
        rendered = {
            "apps": helm("apps", *env_args),
            "gateway": helm("gateway", *env_args),
            "backstage": helm("backstage", *portal_values(environment)),
        }
        kinds = {chart: sorted({d["kind"] for d in docs}) for chart, docs in rendered.items()}
        for problem in unknown_fields(rendered):
            print(f"[{environment}] {problem}")
            failures += 1
        print(f"[{environment}] rendered: " + "; ".join(f"{c}: {len(rendered[c])} objects" for c in kinds))

        with tempfile.TemporaryDirectory() as tmp:
            workloads = pathlib.Path(tmp) / "workloads"
            workloads.mkdir()
            n = 0
            for docs in rendered.values():
                for d in docs:
                    if d["kind"] in ("Deployment", "StatefulSet") and d["metadata"].get("namespace") in MANAGED_NAMESPACES:
                        (workloads / f"{d['metadata']['name']}.yaml").write_text(yaml.safe_dump(d))
                        n += 1
            values = pathlib.Path(tmp) / "values.yaml"
            values.write_text(yaml.safe_dump({
                "apiVersion": "cli.kyverno.io/v1alpha1", "kind": "Values",
                "namespaceSelector": [{"name": ns, "labels": {"platform.fernhill.io/managed": "true"}} for ns in MANAGED_NAMESPACES],
            }))
            result = subprocess.run(["kyverno", "apply", *POLICIES, "--resource", str(workloads), "--values-file", str(values)],
                                    capture_output=True, text=True)
            summary = next((l for l in result.stdout.splitlines() if l.startswith("pass:")), result.stdout.strip()[-200:])
            print(f"[{environment}] {n} platform workloads in managed namespaces -> {summary}")
            if result.returncode != 0:
                print(result.stdout[-2000:], result.stderr[-2000:])
                failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
