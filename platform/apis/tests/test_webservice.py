from conftest import observed

IMAGE = "ghcr.io/fernhill/invoice-api:1.4.2"


def container(out) -> dict:
    return out.one("Deployment")["spec"]["template"]["spec"]["containers"][0]


def test_minimal_service_gets_deployment_service_and_pdb(render):
    out = render("WebService", {"image": IMAGE})

    assert out.kinds() == {"WebService", "Deployment", "Service", "PodDisruptionBudget"}
    assert out.one("Deployment")["spec"]["replicas"] == 2
    assert container(out)["image"] == IMAGE


def test_composed_deployment_satisfies_baseline_policies(render):
    # CI also checks this for real with Kyverno (scripts/check-tenants.py).
    out = render("WebService", {"image": IMAGE})
    labels = out.one("Deployment")["metadata"]["labels"]
    c = container(out)

    ours = {"app.kubernetes.io/name": "invoice-api", "platform.fernhill.io/owner": "billing"}
    # Crossplane adds its own labels (crossplane.io/composite); ours must be there too.
    assert ours.items() <= labels.items()
    assert out.one("Deployment")["spec"]["template"]["metadata"]["labels"] == ours
    assert {"cpu", "memory"} <= c["resources"]["requests"].keys()
    assert "memory" in c["resources"]["limits"]
    assert "readinessProbe" in c


def test_runs_as_non_root_with_read_only_filesystem(render):
    out = render("WebService", {"image": IMAGE})
    pod = out.one("Deployment")["spec"]["template"]["spec"]
    c = container(out)

    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["runAsUser"] == 10001
    assert c["securityContext"]["readOnlyRootFilesystem"] is True
    assert c["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert {"name": "tmp", "mountPath": "/tmp"} in c["volumeMounts"]


def test_probes_use_health_path_and_named_port(render):
    c = container(render("WebService", {"image": IMAGE, "healthPath": "/readyz", "port": 9898}))

    assert c["ports"] == [{"name": "http", "containerPort": 9898}]
    assert c["readinessProbe"]["httpGet"] == {"path": "/readyz", "port": "http"}
    assert c["livenessProbe"]["httpGet"] == {"path": "/readyz", "port": "http"}


def test_single_replica_has_no_pdb_or_spread(render):
    out = render("WebService", {"image": IMAGE, "replicas": 1})

    assert "PodDisruptionBudget" not in out.kinds()
    assert "topologySpreadConstraints" not in out.one("Deployment")["spec"]["template"]["spec"]


def test_expose_adds_route_on_platform_gateway(render):
    out = render("WebService", {"image": IMAGE, "expose": True})
    route = out.one("HTTPRoute")

    assert route["spec"]["hostnames"] == ["invoice-api.billing.localhost"]
    assert route["spec"]["parentRefs"] == [{"name": "platform", "namespace": "gateway"}]
    assert out.one("WebService")["status"]["url"] == "http://invoice-api.billing.localhost"


def test_database_binding_injects_credentials_from_secret(render):
    env = {e["name"]: e for e in container(render("WebService", {"image": IMAGE, "database": "invoice-api"}))["env"]}

    assert env["DATABASE_URL"]["valueFrom"]["secretKeyRef"] == {"name": "invoice-api-app", "key": "uri"}
    pg = {"DATABASE_URL", "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"}
    assert pg <= env.keys()
    # Credentials are referenced, never copied into the Deployment.
    assert all("value" not in env[name] for name in pg)


def test_plain_env_is_passed_through(render):
    env = container(render("WebService", {"image": IMAGE, "env": [{"name": "LOG_LEVEL", "value": "info"}]}))["env"]

    assert {"name": "LOG_LEVEL", "value": "info"} in env


def test_ready_only_when_deployment_available(render):
    def deployment(status):
        return observed("apps/v1", "Deployment", "deployment", "invoice-api", [{"type": "Available", "status": status}])

    assert render("WebService", {"image": IMAGE}).ready() == "False"
    assert render("WebService", {"image": IMAGE}, observed=[deployment("True")]).ready() == "True"
