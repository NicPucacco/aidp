"""Unit tests for the App composition. Run with: make test-apis."""

import importlib.util
import pathlib

from crossplane.function import resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

_spec = importlib.util.spec_from_file_location(
    "app_compose", pathlib.Path(__file__).parent.parent / "compose.py"
)
compose = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compose)

IMAGE = "ghcr.io/fernhill/invoice-api:1.4.2"


def run(spec: dict, observed_deployment: dict | None = None) -> fnv1.RunFunctionResponse:
    req = fnv1.RunFunctionRequest(
        observed=fnv1.State(
            composite=fnv1.Resource(
                resource=resource.dict_to_struct(
                    {
                        "apiVersion": "platform.fernhill.io/v1alpha1",
                        "kind": "App",
                        "metadata": {"name": "invoice-api", "namespace": "billing"},
                        "spec": {"image": IMAGE, **spec},
                    }
                )
            )
        )
    )
    if observed_deployment is not None:
        req.observed.resources["deployment"].resource.update(observed_deployment)
    rsp = fnv1.RunFunctionResponse()
    compose.compose(req, rsp)
    return rsp


def composed(rsp: fnv1.RunFunctionResponse, key: str) -> dict:
    return resource.struct_to_dict(rsp.desired.resources[key].resource)


def container(rsp: fnv1.RunFunctionResponse) -> dict:
    return composed(rsp, "deployment")["spec"]["template"]["spec"]["containers"][0]


def test_minimal_app_gets_deployment_service_and_pdb():
    rsp = run({})

    assert set(rsp.desired.resources) == {"deployment", "service", "pdb"}
    deployment = composed(rsp, "deployment")
    assert deployment["spec"]["replicas"] == 2
    assert container(rsp)["image"] == IMAGE


def test_composed_deployment_satisfies_baseline_policies():
    # The platform must never compose what its own policies (ADR-0005) would
    # reject. CI also checks this for real with kyverno against rendered output.
    rsp = run({})
    deployment = composed(rsp, "deployment")
    labels = deployment["metadata"]["labels"]
    c = container(rsp)

    assert labels["app.kubernetes.io/name"] == "invoice-api"
    assert labels["platform.fernhill.io/owner"] == "billing"
    assert {"cpu", "memory"} <= c["resources"]["requests"].keys()
    assert "memory" in c["resources"]["limits"]
    assert "readinessProbe" in c


def test_runs_as_non_root_with_read_only_filesystem():
    rsp = run({})
    pod = composed(rsp, "deployment")["spec"]["template"]["spec"]
    c = container(rsp)

    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["runAsUser"] == compose.RUN_AS
    assert c["securityContext"]["readOnlyRootFilesystem"] is True
    assert c["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert {"name": "tmp", "mountPath": "/tmp"} in c["volumeMounts"]


def test_probes_use_health_path_and_named_port():
    c = container(run({"healthPath": "/readyz", "port": 9898}))

    assert c["ports"] == [{"name": "http", "containerPort": 9898}]
    assert c["readinessProbe"]["httpGet"] == {"path": "/readyz", "port": "http"}
    assert c["livenessProbe"]["httpGet"] == {"path": "/readyz", "port": "http"}


def test_single_replica_has_no_pdb_or_spread():
    rsp = run({"replicas": 1})

    assert "pdb" not in rsp.desired.resources
    assert "topologySpreadConstraints" not in composed(rsp, "deployment")["spec"]["template"]["spec"]


def test_expose_adds_route_on_platform_gateway():
    rsp = run({"expose": True})
    route = composed(rsp, "route")

    assert route["spec"]["hostnames"] == ["invoice-api.billing.localhost"]
    assert route["spec"]["parentRefs"] == [{"name": "platform", "namespace": "gateway"}]
    status = resource.struct_to_dict(rsp.desired.composite.resource)["status"]
    assert status["url"] == "http://invoice-api.billing.localhost"


def test_database_binding_injects_credentials_from_secret():
    rsp = run({"database": "invoice-api"})
    env = {e["name"]: e for e in container(rsp)["env"]}

    assert env["DATABASE_URL"]["valueFrom"]["secretKeyRef"] == {"name": "invoice-api-app", "key": "uri"}
    assert set(compose.PG_ENV) <= env.keys()
    # Credentials are referenced, never copied into the Deployment.
    assert all("value" not in env[name] for name in compose.PG_ENV)


def test_plain_env_is_passed_through():
    env = container(run({"env": [{"name": "LOG_LEVEL", "value": "info"}]}))["env"]

    assert {"name": "LOG_LEVEL", "value": "info"} in env


def test_ready_only_when_deployment_available():
    assert run({}).desired.resources["deployment"].ready == fnv1.READY_UNSPECIFIED

    available = {"status": {"conditions": [{"type": "Available", "status": "True"}]}}
    assert run({}, available).desired.resources["deployment"].ready == fnv1.READY_TRUE
