"""Render XRs through the real Compositions with `crossplane render`.

The tests exercise the exact artifact the cluster runs (the go-templating
Composition and the pinned function package), not a re-implementation of
it. Needs Docker and the Crossplane CLI (scripts/install-crossplane-cli.sh).
"""

import pathlib
import subprocess

import pytest
import yaml

APIS = pathlib.Path(__file__).resolve().parents[1]
GROUP = "platform.fernhill.io/v1alpha1"
COMPOSITIONS = {"Database": "database", "WebService": "webservice"}


class Rendered:
    def __init__(self, docs: list[dict]):
        self.docs = docs

    def one(self, kind: str) -> dict:
        found = [d for d in self.docs if d["kind"] == kind]
        assert len(found) == 1, f"expected one {kind}, got {[d['kind'] for d in self.docs]}"
        return found[0]

    def kinds(self) -> set[str]:
        return {d["kind"] for d in self.docs}

    def ready(self) -> str:
        xr = next(d for d in self.docs if d["apiVersion"] == GROUP)
        return next(c["status"] for c in xr["status"]["conditions"] if c["type"] == "Ready")


@pytest.fixture
def render(tmp_path):
    def _render(kind: str, spec: dict, observed: list[dict] | None = None, name: str = "invoice-api") -> Rendered:
        xr = {"apiVersion": GROUP, "kind": kind, "metadata": {"name": name, "namespace": "billing"}, "spec": spec}
        (tmp_path / "xr.yaml").write_text(yaml.safe_dump(xr))
        cmd = [
            "crossplane", "render", str(tmp_path / "xr.yaml"),
            str(APIS / COMPOSITIONS[kind] / "composition.yaml"), str(APIS / "functions.yaml"),
        ]
        if observed:
            (tmp_path / "observed.yaml").write_text(yaml.safe_dump_all(observed))
            cmd += ["--observed-resources", str(tmp_path / "observed.yaml")]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        return Rendered([d for d in yaml.safe_load_all(proc.stdout) if d])

    return _render


def observed(api_version: str, kind: str, resource_name: str, name: str, conditions: list[dict]) -> dict:
    """A composed resource as Crossplane would observe it."""
    return {
        "apiVersion": api_version,
        "kind": kind,
        "metadata": {
            "name": name,
            "namespace": "billing",
            "annotations": {"crossplane.io/composition-resource-name": resource_name},
        },
        "status": {"conditions": conditions},
    }
