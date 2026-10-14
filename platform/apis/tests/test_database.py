from conftest import LOCAL_ENV, observed

import yaml

LOCAL = yaml.safe_load(LOCAL_ENV.read_text())["data"]
AZURE = {
    "name": "prod",
    "baseDomain": "platform.fernhill.example",
    "urlPort": "",
    "scheme": "https",
    "database": {
        "backend": "azure-flexible-server",
        "azure": {
            "resourceGroup": "rg-fernhill-prod-data",
            "location": "eastus2",
            "version": "17",
            "skuName": "B_Standard_B1ms",
            "storageMb": 32768,
            "backupRetentionDays": 7,
            "delegatedSubnetID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/v/subnets/snet-postgres",
            "privateDNSZoneID": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/privateDnsZones/fernhill-prod.private.postgres.database.azure.com",
        },
    },
}


# --- local: CloudNativePG ---------------------------------------------------

def test_local_backend_is_cloudnative_pg_sized_by_the_platform(render):
    out = render("Database", {})
    cluster = out.one("Cluster")
    cnpg = LOCAL["database"]["cloudnativePG"]

    assert out.kinds() == {"Database", "Cluster"}
    assert cluster["spec"]["instances"] == cnpg["instances"]
    assert cluster["spec"]["storage"]["size"] == cnpg["storage"]
    assert cluster["spec"]["imageName"] == cnpg["image"]
    assert cluster["spec"]["bootstrap"]["initdb"] == {"database": "app", "owner": "app"}


def test_local_sets_requests_and_memory_limit(render):
    # The platform must not compose anything its own policies would reject.
    resources = render("Database", {}).one("Cluster")["spec"]["resources"]

    assert {"cpu", "memory"} <= resources["requests"].keys()
    assert "memory" in resources["limits"]


def test_local_owner_label_comes_from_team_namespace(render):
    labels = render("Database", {}).one("Cluster")["metadata"]["labels"]

    assert labels["platform.fernhill.io/owner"] == "billing"


def test_local_status_points_at_cnpg_app_secret(render):
    out = render("Database", {"databaseName": "ledger"})
    status = out.one("Database")["status"]

    assert status["backend"] == "cloudnative-pg"
    assert status["connectionSecret"] == "invoice-api-app"
    assert status["host"] == "invoice-api-rw.billing.svc"
    assert out.one("Cluster")["spec"]["bootstrap"]["initdb"]["database"] == "ledger"


def test_local_not_ready_until_cnpg_reports_ready(render):
    def cluster(status):
        return observed("postgresql.cnpg.io/v1", "Cluster", "cluster", "invoice-api", [{"type": "Ready", "status": status}])

    assert render("Database", {}).ready() == "False"
    assert render("Database", {}, observed=[cluster("False")]).ready() == "False"
    assert render("Database", {}, observed=[cluster("True")]).ready() == "True"


# --- AKS: Azure Database for PostgreSQL Flexible Server ----------------------

def test_azure_backend_composes_a_private_flexible_server(render):
    out = render("Database", {"databaseName": "invoices"}, environment=AZURE)
    server = out.one("FlexibleServer")
    fp = server["spec"]["forProvider"]

    assert "Cluster" not in out.kinds()
    assert server["metadata"]["annotations"]["crossplane.io/external-name"] == "prod-billing-invoice-api"
    assert fp["resourceGroupName"] == "rg-fernhill-prod-data"
    assert fp["version"] == "17" and fp["skuName"] == "B_Standard_B1ms"
    assert fp["publicNetworkAccessEnabled"] is False
    assert fp["delegatedSubnetId"].endswith("/subnets/snet-postgres")
    assert fp["autoGeneratePassword"] is True
    assert fp["administratorPasswordSecretRef"] == {"name": "invoice-api-admin", "key": "password"}


def test_azure_keeps_seven_days_of_backups(render):
    fp = render("Database", {}, environment=AZURE).one("FlexibleServer")["spec"]["forProvider"]

    assert fp["backupRetentionDays"] == 7


def test_azure_server_carries_team_tags(render):
    tags = render("Database", {}, environment=AZURE).one("FlexibleServer")["spec"]["forProvider"]["tags"]

    assert tags == {"team": "billing", "database": "invoice-api", "environment": "prod", "managed-by": "crossplane"}


def test_azure_resources_are_never_deleted_by_crossplane(render):
    # Deleting a Database keeps the server and its backups (ADR-0019).
    out = render("Database", {}, environment=AZURE)

    for kind in ("FlexibleServer", "FlexibleServerDatabase"):
        policies = out.one(kind)["spec"]["managementPolicies"]
        assert "Delete" not in policies and "*" not in policies, kind


def test_azure_creates_the_requested_database_on_the_server(render):
    db = render("Database", {"databaseName": "invoices"}, environment=AZURE).one("FlexibleServerDatabase")

    assert db["metadata"]["annotations"]["crossplane.io/external-name"] == "invoices"
    assert db["spec"]["forProvider"]["serverIdRef"] == {"name": "invoice-api"}


def test_azure_publishes_the_same_secret_contract_once_credentials_exist(render):
    # Before the provider has created the server there are no credentials, so
    # no "<name>-app" Secret yet; the XR already names it. (crossplane render
    # can't simulate connection details; the e2e on AKS covers the populated case.)
    out = render("Database", {}, environment=AZURE)

    assert "Secret" not in out.kinds()
    assert out.one("Database")["status"]["connectionSecret"] == "invoice-api-app"
    assert out.one("Database")["status"]["backend"] == "azure-flexible-server"
    assert out.ready() == "False"


def test_azure_ready_only_when_server_and_database_are(render):
    server = observed("dbforpostgresql.azure.m.upbound.io/v1beta1", "FlexibleServer", "server", "invoice-api",
                      [{"type": "Ready", "status": "True"}])
    server["status"]["atProvider"] = {"fqdn": "prod-billing-invoice-api.postgres.database.azure.com"}

    out = render("Database", {}, observed=[server], environment=AZURE)

    assert out.one("Database")["status"]["host"] == "prod-billing-invoice-api.postgres.database.azure.com"
    assert out.ready() == "False", "the database (and Secret) aren't ready yet"
