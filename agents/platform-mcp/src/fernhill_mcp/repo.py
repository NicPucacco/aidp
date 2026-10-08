"""Read-only view of the platform repo: teams, catalog, golden paths, APIs.

Everything the server knows comes from Git, the same files Backstage and
Argo CD read. There is no separate agent-facing data model to drift.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

import yaml

GROUP = "platform.fernhill.io"


def find_root(start: pathlib.Path | None = None) -> pathlib.Path:
    """FERNHILL_REPO, else the nearest ancestor containing platform/apis."""
    if env := os.environ.get("FERNHILL_REPO"):
        return pathlib.Path(env).resolve()
    here = (start or pathlib.Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "platform" / "apis").is_dir():
            return candidate
    raise RuntimeError("Can't find the platform repo; set FERNHILL_REPO.")


def _load_all(path: pathlib.Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


@dataclass(frozen=True)
class Repo:
    root: pathlib.Path

    # --- organisation -----------------------------------------------------

    def teams(self) -> list[str]:
        return sorted(
            d["metadata"]["name"]
            for d in _load_all(self.root / "catalog" / "org.yaml")
            if d.get("kind") == "Group" and d.get("spec", {}).get("type") == "team"
        )

    def tenant_dir(self, team: str, name: str) -> pathlib.Path:
        return self.root / "tenants" / team / name

    def tenant_objects(self, team: str | None = None) -> list[dict]:
        """Platform API objects declared under tenants/, with their team."""
        out = []
        base = self.root / "tenants"
        for team_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            if team and team_dir.name != team:
                continue
            for path in sorted(team_dir.rglob("*.y*ml")):
                if path.name == "catalog-info.yaml":
                    continue
                for doc in _load_all(path):
                    if doc.get("apiVersion", "").startswith(GROUP):
                        out.append(
                            {
                                "team": team_dir.name,
                                "kind": doc["kind"],
                                "name": doc["metadata"]["name"],
                                "spec": doc.get("spec", {}),
                                "path": str(path.relative_to(self.root)),
                            }
                        )
        return out

    # --- catalog ------------------------------------------------------------

    def catalog_entities(self) -> list[dict]:
        files = sorted((self.root / "catalog").glob("*.yaml"))
        files += sorted((self.root / "tenants").glob("*/*/catalog-info.yaml"))
        entities = []
        for path in files:
            for doc in _load_all(path):
                spec = doc.get("spec", {})
                entities.append(
                    {
                        "kind": doc["kind"],
                        "name": doc["metadata"]["name"],
                        "description": doc["metadata"].get("description", ""),
                        "owner": spec.get("owner", ""),
                        "type": spec.get("type", ""),
                        "source": str(path.relative_to(self.root)),
                    }
                )
        return entities

    # --- golden paths and APIs ----------------------------------------------

    def golden_paths(self) -> dict[str, dict]:
        paths = {}
        for template in sorted((self.root / "golden-paths").glob("*/template.yaml")):
            doc = yaml.safe_load(template.read_text())
            paths[doc["metadata"]["name"]] = {
                "title": doc["metadata"]["title"],
                "description": " ".join(doc["metadata"]["description"].split()),
                "dir": template.parent,
            }
        return paths

    def api_schema(self, kind: str) -> dict:
        """The openAPIV3Schema `spec` of a platform API, from its XRD."""
        for definition in (self.root / "platform" / "apis").glob("*/definition.yaml"):
            xrd = yaml.safe_load(definition.read_text())
            if xrd["spec"]["names"]["kind"] == kind:
                version = xrd["spec"]["versions"][0]
                return {
                    "apiVersion": f"{GROUP}/{version['name']}",
                    "kind": kind,
                    "spec": version["schema"]["openAPIV3Schema"]["properties"]["spec"],
                }
        raise KeyError(kind)

    def api_kinds(self) -> list[str]:
        return sorted(
            yaml.safe_load(p.read_text())["spec"]["names"]["kind"]
            for p in (self.root / "platform" / "apis").glob("*/definition.yaml")
        )
