#!/usr/bin/env python3
"""Check tenant config the way the cluster will see it, before review.

For every file under tenants/<team>/:
  1. Boundary checks (ADR-0007): only platform.fernhill.io kinds, and no
     metadata.namespace (the platform decides the namespace).
  2. Render each object through its real Composition with `crossplane render`
     (runs the same function-python package the cluster runs).
  3. Evaluate the rendered resources against the real Kyverno policies, with
     each team namespace labelled the way the ApplicationSet labels it.

This is what makes a tenant PR, from a human or an agent, cheap to review:
by the time someone looks at it, it's known to compose and to pass policy.

Usage: scripts/check-tenants.py [--keep DIR]
Needs: crossplane CLI, kyverno CLI, Docker, PyYAML.
"""

import pathlib
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
TENANTS = ROOT / "tenants"
APIS = ROOT / "platform" / "apis"
POLICIES = ROOT / "platform" / "policies"
GROUP = "platform.fernhill.io"

# XR kind -> API directory (holds composition.yaml).
KINDS = {"Database": "database", "App": "app"}


def tenant_objects():
    for team_dir in sorted(p for p in TENANTS.iterdir() if p.is_dir()):
        for path in sorted(team_dir.rglob("*.y*ml")):
            for doc in yaml.safe_load_all(path.read_text()):
                if doc:
                    yield team_dir.name, path.relative_to(ROOT), doc


def boundary_errors(path, doc):
    errors = []
    group = doc.get("apiVersion", "").split("/")[0]
    if group != GROUP:
        errors.append(f"{path}: {doc.get('kind')} ({group or 'core'}) isn't a platform API; tenants may only declare {GROUP} kinds")
    elif doc.get("kind") not in KINDS:
        errors.append(f"{path}: unknown platform kind {doc.get('kind')}")
    if "namespace" in doc.get("metadata", {}):
        errors.append(f"{path}: metadata.namespace must not be set; the platform assigns the team namespace")
    return errors


def render(team, doc, workdir):
    xr = dict(doc, metadata=dict(doc["metadata"], namespace=team))
    xr_path = workdir / f"xr-{team}-{doc['kind']}-{doc['metadata']['name']}.yaml"
    xr_path.write_text(yaml.safe_dump(xr))
    api = APIS / KINDS[doc["kind"]]
    out = subprocess.run(
        ["crossplane", "render", str(xr_path), str(api / "composition.yaml"), str(APIS / "functions.yaml")],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rendered = []
    for obj in yaml.safe_load_all(out):
        if not obj or obj.get("apiVersion", "").startswith(GROUP) or obj.get("kind") == "Result":
            continue
        obj.setdefault("metadata", {}).setdefault("namespace", team)
        rendered.append(obj)
    return rendered


def main() -> int:
    keep = sys.argv[sys.argv.index("--keep") + 1] if "--keep" in sys.argv else None
    objects = list(tenant_objects())

    errors = [e for _, path, doc in objects for e in boundary_errors(path, doc)]
    if errors:
        print("Tenant boundary violations:", *errors, sep="\n  ")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        workdir = pathlib.Path(keep or tmp)
        workdir.mkdir(parents=True, exist_ok=True)
        rendered_dir = workdir / "rendered"
        rendered_dir.mkdir(exist_ok=True)

        teams = set()
        for team, path, doc in objects:
            teams.add(team)
            resources = render(team, doc, workdir)
            out = rendered_dir / f"{team}-{doc['kind'].lower()}-{doc['metadata']['name']}.yaml"
            out.write_text(yaml.safe_dump_all(resources))
            kinds = ", ".join(sorted(r["kind"] for r in resources))
            print(f"rendered {path} -> {kinds}")

        values = workdir / "values.yaml"
        values.write_text(
            yaml.safe_dump(
                {
                    "apiVersion": "cli.kyverno.io/v1alpha1",
                    "kind": "Values",
                    "namespaceSelector": [
                        {"name": t, "labels": {"platform.fernhill.io/managed": "true"}} for t in sorted(teams)
                    ],
                }
            )
        )
        policies = sorted(str(p) for p in POLICIES.glob("*.yaml"))
        result = subprocess.run(
            ["kyverno", "apply", *policies, "--resource", str(rendered_dir), "--values-file", str(values)],
            capture_output=True,
            text=True,
        )
        print(result.stdout[-3000:], result.stderr[-3000:], sep="")
        return result.returncode


if __name__ == "__main__":
    sys.exit(main())
