import json

import httpx
import pytest
import respx

from fernhill_mcp.github import AGENT_LABEL, GitHub
from fernhill_mcp.server import build_server

# anyio ships with the MCP SDK; its pytest plugin runs the async tests.
pytestmark = pytest.mark.anyio

REASON = "Tracking needs somewhere to store scan events for the new depot."


def result(call) -> dict | list:
    """A tool's return value, whether it came back structured or as JSON text."""
    assert not call.is_error, call.content
    sc = call.structured_content
    if sc is not None:
        return sc.get("result", sc)
    return json.loads(call.content[0].text)


@pytest.fixture
def server(repo):
    return build_server(repo)


async def test_exposes_read_and_propose_tools(server):
    tools = {t.name: t for t in await server.list_tools()}

    assert {"list_teams", "list_golden_paths", "describe_api", "search_catalog",
            "list_team_resources", "propose_webservice", "propose_database",
            "get_proposal_status"} <= tools.keys()
    assert tools["search_catalog"].annotations.read_only_hint is True
    assert tools["propose_database"].annotations.read_only_hint is False


async def test_read_tools_reflect_the_repo(server):
    assert "billing" in result(await server.call_tool("list_teams", {}))
    found = result(await server.call_tool("search_catalog", {"query": "invoice"}))
    assert {"invoice-api", "invoice-api-db"} <= {e["name"] for e in found}
    schema = result(await server.call_tool("describe_api", {"kind": "Database"}))
    assert schema["spec"]["properties"]["size"]["enum"] == ["small", "medium", "large"]


async def test_propose_defaults_to_dry_run(server):
    out = result(await server.call_tool(
        "propose_database", {"team": "tracking", "name": "tracking-events", "reason": REASON}
    ))

    assert out["ok"] and out["pull_request"] is None
    assert "dry run" in out["note"]
    assert "tenants/tracking/tracking-events/database.yaml" in out["files"]


async def test_without_credentials_nothing_is_written(server):
    out = result(await server.call_tool(
        "propose_database", {"team": "tracking", "name": "tracking-events", "reason": REASON, "dry_run": False}
    ))

    assert out["pull_request"] is None
    assert "No GitHub credentials" in out["note"]


@respx.mock(base_url="https://api.github.com")
def test_open_pull_request_is_one_commit_on_an_agent_branch_with_a_label(respx_mock):
    repo = "/repos/NicPucacco/aidp"
    respx_mock.get(f"{repo}/git/ref/heads/main").respond(json={"object": {"sha": "base"}})
    respx_mock.get(f"{repo}/git/commits/base").respond(json={"tree": {"sha": "basetree"}})
    tree = respx_mock.post(f"{repo}/git/trees").respond(json={"sha": "newtree"})
    commit = respx_mock.post(f"{repo}/git/commits").respond(json={"sha": "newcommit"})
    ref = respx_mock.post(f"{repo}/git/refs").respond(json={})
    respx_mock.post(f"{repo}/pulls").respond(json={"number": 7, "html_url": "https://github.com/NicPucacco/aidp/pull/7"})
    label = respx_mock.post(f"{repo}/issues/7/labels").respond(json=[])

    gh = GitHub("t", "NicPucacco/aidp", client=httpx.Client(base_url="https://api.github.com"))
    pr = gh.open_pull_request(
        base="main", branch="agent/tracking/tracking-events",
        files={"tenants/tracking/tracking-events/database.yaml": "x"},
        title="t", body="b", commit_message="m",
    )

    assert pr == {"number": 7, "url": "https://github.com/NicPucacco/aidp/pull/7",
                  "branch": "agent/tracking/tracking-events", "commit": "newcommit"}
    assert json.loads(tree.calls[0].request.content)["base_tree"] == "basetree"
    assert json.loads(commit.calls[0].request.content)["parents"] == ["base"]
    assert json.loads(ref.calls[0].request.content)["ref"] == "refs/heads/agent/tracking/tracking-events"
    assert json.loads(label.calls[0].request.content) == {"labels": [AGENT_LABEL]}
