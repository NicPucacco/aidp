"""Unit tests for the Database composition.

Run with: make test-apis (pytest, same SDK version function-python ships).
"""

import importlib.util
import pathlib

import pytest
from crossplane.function import resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

_spec = importlib.util.spec_from_file_location(
    "database_compose", pathlib.Path(__file__).parent.parent / "compose.py"
)
compose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compose)


def run(spec: dict, observed_cluster: dict | None = None) -> fnv1.RunFunctionResponse:
    req = fnv1.RunFunctionRequest(
        observed=fnv1.State(
            composite=fnv1.Resource(
                resource=resource.dict_to_struct(
                    {
                        "apiVersion": "platform.fernhill.io/v1alpha1",
                        "kind": "Database",
                        "metadata": {"name": "invoices", "namespace": "billing"},
                        "spec": spec,
                    }
                )
            )
        )
    )
    if observed_cluster is not None:
        req.observed.resources["cluster"].resource.update(observed_cluster)
    rsp = fnv1.RunFunctionResponse()
    compose.compose(req, rsp)
    return rsp


def desired_cluster(rsp: fnv1.RunFunctionResponse) -> dict:
    return resource.struct_to_dict(rsp.desired.resources["cluster"].resource)


def test_defaults_to_small_postgres_18():
    cluster = desired_cluster(run({}))

    assert cluster["kind"] == "Cluster"
    assert cluster["metadata"]["name"] == "invoices"
    assert cluster["spec"]["instances"] == 1
    assert cluster["spec"]["storage"]["size"] == "1Gi"
    assert cluster["spec"]["imageName"].endswith(":18.6")
    assert cluster["spec"]["bootstrap"]["initdb"] == {"database": "app", "owner": "app"}


@pytest.mark.parametrize(
    ("size", "instances", "storage"),
    [("small", 1, "1Gi"), ("medium", 2, "10Gi"), ("large", 3, "50Gi")],
)
def test_sizes_map_to_instances_and_storage(size, instances, storage):
    cluster = desired_cluster(run({"size": size}))

    assert cluster["spec"]["instances"] == instances
    assert cluster["spec"]["storage"]["size"] == storage


def test_every_size_sets_requests_and_memory_limit():
    # Mirrors the require-resources policy: the platform must not compose
    # anything it would reject from a tenant.
    for size in compose.SIZES:
        resources = desired_cluster(run({"size": size}))["spec"]["resources"]
        assert {"cpu", "memory"} <= resources["requests"].keys()
        assert "memory" in resources["limits"]


def test_every_version_has_a_pinned_image():
    for version, image in compose.IMAGES.items():
        assert image.rsplit(":", 1)[1].startswith(f"{version}.")


def test_owner_label_comes_from_team_namespace():
    labels = desired_cluster(run({}))["metadata"]["labels"]

    assert labels["platform.fernhill.io/owner"] == "billing"


def test_status_points_at_cnpg_app_secret():
    rsp = run({"databaseName": "ledger"})
    status = resource.struct_to_dict(rsp.desired.composite.resource)["status"]

    assert status == {
        "connectionSecret": "invoices-app",
        "host": "invoices-rw.billing.svc",
        "port": 5432,
    }
    assert desired_cluster(rsp)["spec"]["bootstrap"]["initdb"]["database"] == "ledger"


def test_not_ready_until_cnpg_reports_ready():
    assert run({}).desired.resources["cluster"].ready == fnv1.READY_UNSPECIFIED

    not_ready = {"status": {"conditions": [{"type": "Ready", "status": "False"}]}}
    assert run({}, not_ready).desired.resources["cluster"].ready == fnv1.READY_UNSPECIFIED

    ready = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
    assert run({}, ready).desired.resources["cluster"].ready == fnv1.READY_TRUE
