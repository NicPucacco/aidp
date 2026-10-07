"""Compose a Fernhill Database into a CloudNativePG Cluster.

This file is the source of truth. scripts/gen-compositions.py embeds it into
composition.yaml for function-python to run; CI fails if the two drift.
"""

from crossplane.function import resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

# What each t-shirt size means. This table is the platform team's contract
# with tenants: changing it changes every database of that size on next sync.
SIZES = {
    "small": {
        "instances": 1,
        "storage": "1Gi",
        "requests": {"cpu": "100m", "memory": "256Mi"},
        "limits": {"memory": "512Mi"},
    },
    "medium": {
        "instances": 2,
        "storage": "10Gi",
        "requests": {"cpu": "250m", "memory": "1Gi"},
        "limits": {"memory": "1Gi"},
    },
    "large": {
        "instances": 3,
        "storage": "50Gi",
        "requests": {"cpu": "1", "memory": "4Gi"},
        "limits": {"memory": "4Gi"},
    },
}

# Patch versions are pinned here so a minor upgrade is a reviewed PR, not a
# side effect of a pod restarting.
IMAGES = {
    "16": "ghcr.io/cloudnative-pg/postgresql:16.15",
    "17": "ghcr.io/cloudnative-pg/postgresql:17.11",
    "18": "ghcr.io/cloudnative-pg/postgresql:18.6",
}


def compose(req: fnv1.RunFunctionRequest, rsp: fnv1.RunFunctionResponse):
    xr = resource.struct_to_dict(req.observed.composite.resource)
    name = xr["metadata"]["name"]
    namespace = xr["metadata"]["namespace"]
    spec = xr.get("spec", {})
    size = SIZES[spec.get("size", "small")]
    database = spec.get("databaseName", "app")

    resource.update(
        rsp.desired.resources["cluster"],
        {
            "apiVersion": "postgresql.cnpg.io/v1",
            "kind": "Cluster",
            "metadata": {
                "name": name,
                "labels": {
                    "app.kubernetes.io/name": name,
                    "app.kubernetes.io/component": "database",
                    # Team namespaces are named after the team (ApplicationSet
                    # in platform/apps/templates/tenants.yaml).
                    "platform.fernhill.io/owner": namespace,
                },
            },
            "spec": {
                "instances": size["instances"],
                "imageName": IMAGES[spec.get("version", "18")],
                "storage": {"size": size["storage"]},
                "resources": {
                    "requests": size["requests"],
                    "limits": size["limits"],
                },
                "bootstrap": {
                    "initdb": {"database": database, "owner": database},
                },
            },
        },
    )

    # CloudNativePG writes connection details to "<cluster>-app".
    resource.update(
        rsp.desired.composite,
        {
            "status": {
                "connectionSecret": f"{name}-app",
                "host": f"{name}-rw.{namespace}.svc",
                "port": 5432,
            }
        },
    )

    if _cluster_ready(req):
        rsp.desired.resources["cluster"].ready = fnv1.READY_TRUE


def _cluster_ready(req: fnv1.RunFunctionRequest) -> bool:
    if "cluster" not in req.observed.resources:
        return False
    observed = resource.struct_to_dict(req.observed.resources["cluster"].resource)
    conditions = observed.get("status", {}).get("conditions", [])
    return any(c.get("type") == "Ready" and c.get("status") == "True" for c in conditions)
