import pytest

from conftest import observed


def test_defaults_to_small_postgres_18(render):
    cluster = render("Database", {}).one("Cluster")

    assert cluster["metadata"]["name"] == "invoice-api"
    assert cluster["spec"]["instances"] == 1
    assert cluster["spec"]["storage"]["size"] == "1Gi"
    assert cluster["spec"]["imageName"].endswith(":18.6")
    assert cluster["spec"]["bootstrap"]["initdb"] == {"database": "app", "owner": "app"}


@pytest.mark.parametrize(
    ("size", "instances", "storage"),
    [("small", 1, "1Gi"), ("medium", 2, "10Gi"), ("large", 3, "50Gi")],
)
def test_sizes_map_to_instances_and_storage(render, size, instances, storage):
    cluster = render("Database", {"size": size}).one("Cluster")

    assert cluster["spec"]["instances"] == instances
    assert cluster["spec"]["storage"]["size"] == storage


@pytest.mark.parametrize("size", ["small", "medium", "large"])
def test_every_size_sets_requests_and_memory_limit(render, size):
    # The platform must not compose anything its own policies would reject.
    resources = render("Database", {"size": size}).one("Cluster")["spec"]["resources"]

    assert {"cpu", "memory"} <= resources["requests"].keys()
    assert "memory" in resources["limits"]


@pytest.mark.parametrize("version", ["16", "17", "18"])
def test_every_version_has_a_pinned_image(render, version):
    image = render("Database", {"version": version}).one("Cluster")["spec"]["imageName"]

    assert image.rsplit(":", 1)[1].startswith(f"{version}.")


def test_owner_label_comes_from_team_namespace(render):
    labels = render("Database", {}).one("Cluster")["metadata"]["labels"]

    assert labels["platform.fernhill.io/owner"] == "billing"


def test_status_points_at_cnpg_app_secret(render):
    out = render("Database", {"databaseName": "ledger"})
    status = out.one("Database")["status"]

    assert status["connectionSecret"] == "invoice-api-app"
    assert status["host"] == "invoice-api-rw.billing.svc"
    assert status["port"] == 5432
    assert out.one("Cluster")["spec"]["bootstrap"]["initdb"]["database"] == "ledger"


def test_not_ready_until_cnpg_reports_ready(render):
    def cluster(status):
        return observed("postgresql.cnpg.io/v1", "Cluster", "cluster", "invoice-api", [{"type": "Ready", "status": status}])

    assert render("Database", {}).ready() == "False"
    assert render("Database", {}, observed=[cluster("False")]).ready() == "False"
    assert render("Database", {}, observed=[cluster("True")]).ready() == "True"
