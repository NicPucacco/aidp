"""MCP server: the Fernhill platform as tools an agent can use (ADR-0012).

Read tools answer "what exists and what can I ask for?". Propose tools
render a golden path and open a pull request. That's the only thing this
server can change. Every tool is safe to call speculatively: proposals are
validated before anything is written, and `dry_run` returns the files.
"""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import proposals as P
from .github import GitHub, identity_from_env
from .repo import Repo, find_root

INSTRUCTIONS = """\
You are working with Fernhill's internal developer platform. Every change is a
pull request against the platform repo; you cannot change the cluster directly.

To request infrastructure:
1. Call list_golden_paths and describe_api to see what you can ask for.
2. Call propose_webservice or propose_database with dry_run=true first and fix
   any problems it reports.
3. Call it again with dry_run=false to open the pull request. Always give a
   real reason: it becomes the PR's "Why" section and reviewers rely on it.
4. Call get_proposal_status to watch CI and review. If CI fails, read the
   failure and propose again with a new name, or tell the human what's wrong.

A human must approve and merge every PR. Agents may request at most 'medium'
sizes and 3 replicas; for anything bigger, ask a human to open the PR.
"""

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
PROPOSE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)


def build_server(repo: Repo | None = None) -> MCPServer:
    repo = repo or Repo(find_root())
    agent = os.environ.get("FERNHILL_AGENT_NAME", "unknown-agent")
    github_repo = os.environ.get("FERNHILL_GITHUB_REPO", "NicPucacco/aidp")
    base_branch = os.environ.get("FERNHILL_BASE_BRANCH", "main")

    server = MCPServer(name="fernhill-platform", title="Fernhill Platform", instructions=INSTRUCTIONS, version="0.1.0")

    def _publish(p: P.Proposal, dry_run: bool) -> dict:
        result = {
            "ok": p.ok,
            "problems": p.problems,
            "files": p.files,
            "pull_request": None,
        }
        if not p.ok or dry_run:
            result["note"] = "Not opened: " + ("fix the problems above." if not p.ok else "dry run.")
            return result
        ident = identity_from_env()
        if ident.kind == "none":
            result["note"] = "No GitHub credentials configured; returned the files instead (see docs/agents.md)."
            return result
        message = f"{p.title}\n\n{p.reason.strip()}\n\nAgent: {p.agent}\nRequested-via: fernhill-platform-mcp ({ident.kind})"
        result["pull_request"] = GitHub(ident.token, github_repo).open_pull_request(
            base=base_branch, branch=p.branch, files=p.files, title=p.title, body=p.body(), commit_message=message
        )
        result["identity"] = ident.kind
        return result

    @server.tool(annotations=READ)
    def list_teams() -> list[str]:
        """Teams that can own services and databases. Use one as `team` in proposals."""
        return repo.teams()

    @server.tool(annotations=READ)
    def list_golden_paths() -> dict:
        """Supported ways to request infrastructure, and the platform APIs behind them."""
        return {
            "golden_paths": {k: {"title": v["title"], "description": v["description"]} for k, v in repo.golden_paths().items()},
            "apis": repo.api_kinds(),
            "agent_limits": P.AGENT_LIMITS,
        }

    @server.tool(annotations=READ)
    def describe_api(kind: str) -> dict:
        """JSON schema of a platform API's spec (e.g. 'WebService', 'Database'), straight from its XRD."""
        return repo.api_schema(kind)

    @server.tool(annotations=READ)
    def search_catalog(query: str = "", kind: str = "") -> list[dict]:
        """Search the software catalog (services, databases, teams, APIs) by name or description."""
        q, k = query.lower(), kind.lower()
        return [
            e
            for e in repo.catalog_entities()
            if (not k or e["kind"].lower() == k) and (q in e["name"].lower() or q in e["description"].lower())
        ]

    @server.tool(annotations=READ)
    def list_team_resources(team: str) -> list[dict]:
        """Platform objects (WebServices, Databases) a team has declared, with their specs."""
        return repo.tenant_objects(team)

    @server.tool(annotations=PROPOSE)
    def propose_webservice(
        team: str,
        name: str,
        image: str,
        reason: str,
        description: str = "",
        port: int = 8080,
        health_path: str = "/healthz",
        size: str = "small",
        replicas: int = 2,
        expose: bool = True,
        database_size: str | None = None,
        database_name: str = "app",
        dry_run: bool = True,
    ) -> dict:
        """Request a new web service (and optionally its own Postgres) as a pull request.

        `image` must be pinned (tag or digest). Set `database_size` to give the
        service a database; its credentials are injected as DATABASE_URL.
        Runs as a dry run unless dry_run=false.
        """
        return _publish(
            P.propose_webservice(
                repo, agent=agent, team=team, name=name, image=image, reason=reason, description=description,
                port=port, health_path=health_path, size=size, replicas=replicas, expose=expose,
                database_size=database_size, database_name=database_name,
            ),
            dry_run,
        )

    @server.tool(annotations=PROPOSE)
    def propose_database(
        team: str, name: str, reason: str, size: str = "small", database_name: str = "app", dry_run: bool = True
    ) -> dict:
        """Request a standalone Postgres database as a pull request. Runs as a dry run unless dry_run=false."""
        return _publish(
            P.propose_database(repo, agent=agent, team=team, name=name, reason=reason, size=size, database_name=database_name),
            dry_run,
        )

    @server.tool(annotations=READ)
    def get_proposal_status(pr_number: int) -> dict:
        """CI checks, reviews, and state of a proposal's pull request."""
        ident = identity_from_env()
        if ident.kind == "none":
            return {"error": "No GitHub credentials configured."}
        return GitHub(ident.token, github_repo).pull_request_status(pr_number)

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
