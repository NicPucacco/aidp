import re

import pytest
import yaml

from fernhill_mcp import proposals as P

REASON = "Routing needs a planner service to replace the nightly batch job."


def objects(p: P.Proposal) -> dict[str, dict]:
    out = {}
    for path, content in p.files.items():
        for doc in yaml.safe_load_all(content):
            if doc:
                out[f"{path.rsplit('/', 1)[1]}:{doc['kind']}"] = doc
    return out


def test_webservice_with_database_renders_golden_path_files(repo):
    p = P.propose_webservice(
        repo, agent="test-agent", team="routing", name="route-planner",
        image="ghcr.io/fernhill/route-planner:0.3.1", reason=REASON, database_size="small",
    )

    assert p.ok, p.problems
    assert set(p.files) == {
        "tenants/routing/route-planner/webservice.yaml",
        "tenants/routing/route-planner/database.yaml",
        "tenants/routing/route-planner/catalog-info.yaml",
    }
    objs = objects(p)
    assert objs["webservice.yaml:WebService"]["spec"]["database"] == "route-planner"
    assert objs["catalog-info.yaml:Component"]["spec"]["owner"] == "group:routing"


def test_platform_objects_are_stamped_as_agent_requested(repo):
    p = P.propose_database(repo, agent="claude-code", team="tracking", name="tracking-events", reason=REASON)

    db = objects(p)["database.yaml:Database"]
    assert db["metadata"]["annotations"][P.REQUESTED_BY] == "agent:claude-code"
    # Backstage entities aren't stamped; they aren't platform objects.
    assert "annotations" not in objects(p)["catalog-info.yaml:Resource"]["metadata"]


def test_no_database_means_no_database_file(repo):
    p = P.propose_webservice(repo, agent="a", team="routing", name="route-planner", image="x/y:1.0", reason=REASON)

    assert not any(path.endswith("database.yaml") for path in p.files)
    assert "database" not in objects(p)["webservice.yaml:WebService"]["spec"]


@pytest.mark.parametrize(
    ("kwargs", "problem"),
    [
        ({"team": "marketing"}, "Unknown team"),
        ({"name": "Route_Planner"}, "must match"),
        ({"team": "billing", "name": "invoice-api"}, "already exists"),
        ({"reason": "need it"}, "Give a reason"),
        ({"image": "ghcr.io/fernhill/route-planner:latest"}, ":latest"),
        ({"image": "ghcr.io/fernhill/route-planner"}, "does not match"),
        ({"size": "large"}, "at most 'medium'"),
        ({"replicas": 5}, "at most 3 replicas"),
        ({"size": "huge"}, "is not one of"),
    ],
)
def test_problems_are_reported_before_anything_is_written(repo, kwargs, problem):
    args = dict(agent="a", team="routing", name="route-planner", image="ghcr.io/fernhill/route-planner:0.3.1", reason=REASON)
    p = P.propose_webservice(repo, **(args | kwargs))

    assert not p.ok
    assert any(problem in msg for msg in p.problems), p.problems


def test_pr_body_leads_with_why(repo):
    p = P.propose_database(repo, agent="claude-code", team="tracking", name="tracking-events", reason=REASON)

    assert p.body().startswith(f"## Why\n\n{REASON}")
    assert "agent `claude-code`" in p.body()
    assert p.branch == "agent/tracking/tracking-events"


def test_fast_feedback_limits_match_the_admission_policy(repo):
    # The MCP server's limits are UX; platform/policies/agent-limits.yaml is
    # the authority. They must agree, or agents get advice CI then rejects.
    policy = (repo.root / "platform" / "policies" / "agent-limits.yaml").read_text()
    forbidden = P.SIZES[P.SIZES.index(P.AGENT_LIMITS["max_size"]) + 1 :]
    for size in forbidden:
        assert f"!= '{size}'" in policy
    assert re.search(rf"replicas\.orValue\(\d+\) <= {P.AGENT_LIMITS['max_replicas']}\b", policy)
