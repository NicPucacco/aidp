"""Turn an agent's request into tenant files, using the golden-path skeletons.

Agents and humans get identical output: this renders the same skeletons
Backstage renders (golden-paths/), so there is one definition of what a new
service or database looks like (ADR-0012). The only difference is an
annotation recording that an agent asked for it, which admission policy
uses to apply agent-specific limits (ADR-0013).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import jinja2
import jsonschema
import yaml

from .repo import GROUP, Repo

REQUESTED_BY = f"{GROUP}/requested-by"
NAME = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$")

# Fast feedback for agents. The authoritative copy of these limits is
# platform/policies/agent-limits.yaml, enforced in CI and at admission;
# tests/test_proposals.py checks the two agree.
AGENT_LIMITS = {
    "max_size": "medium",
    "max_replicas": 3,
}
SIZES = ["small", "medium", "large"]

_env = jinja2.Environment(
    variable_start_string="${{",
    variable_end_string="}}",
    keep_trailing_newline=True,
    undefined=jinja2.StrictUndefined,
    # Backstage renders JS booleans: true/false, not True/False.
    finalize=lambda v: str(v).lower() if isinstance(v, bool) else v,
)


@dataclass
class Proposal:
    team: str
    name: str
    golden_path: str
    reason: str
    agent: str
    files: dict[str, str] = field(default_factory=dict)  # repo-relative path -> content
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def branch(self) -> str:
        return f"agent/{self.team}/{self.name}"

    @property
    def title(self) -> str:
        what = {"new-webservice": "New web service", "new-database": "New database"}[self.golden_path]
        return f"[{self.team}] {what}: {self.name}"

    def body(self) -> str:
        files = "\n".join(f"- `{p}`" for p in sorted(self.files))
        return (
            f"## Why\n\n{self.reason.strip()}\n\n"
            f"## What\n\nGolden path **{self.golden_path}** for team `{self.team}`:\n\n{files}\n\n"
            "## Checks before opening\n\n"
            "- Rendered from the same skeletons as the developer portal\n"
            "- Validated against the platform API schemas\n"
            f"- Within agent limits (size ≤ {AGENT_LIMITS['max_size']}, replicas ≤ {AGENT_LIMITS['max_replicas']})\n\n"
            "CI renders these files through the real compositions and policies before review "
            "(ADR-0009). A human must approve and merge (ADR-0001).\n\n"
            f"---\nOpened by `fernhill-platform-mcp` on behalf of agent `{self.agent}`."
        )


def _render_dir(repo: Repo, skeleton: str, values: dict) -> dict[str, str]:
    out = {}
    for src in sorted((repo.root / "golden-paths" / skeleton).rglob("*")):
        if src.is_file():
            out[src.name] = _env.from_string(src.read_text()).render({"values": values})
    return out


def _annotate(content: str, agent: str) -> str:
    """Stamp platform API objects with who asked for them."""
    docs = [d for d in yaml.safe_load_all(content) if d]
    for doc in docs:
        if doc.get("apiVersion", "").startswith(GROUP):
            doc["metadata"].setdefault("annotations", {})[REQUESTED_BY] = f"agent:{agent}"
    return yaml.safe_dump_all(docs, sort_keys=False)


def _validate(repo: Repo, proposal: Proposal) -> None:
    p = proposal
    if p.team not in repo.teams():
        p.problems.append(f"Unknown team '{p.team}'. Known teams: {', '.join(repo.teams())}.")
    if not NAME.match(p.name):
        p.problems.append(f"Name '{p.name}' must match {NAME.pattern}.")
    if repo.tenant_dir(p.team, p.name).exists():
        p.problems.append(f"tenants/{p.team}/{p.name} already exists; agents can only propose new resources.")
    if len(p.reason.strip()) < 20:
        p.problems.append("Give a reason (at least a sentence). It becomes the PR's 'Why' section, which reviewers rely on.")

    for path, content in p.files.items():
        for doc in yaml.safe_load_all(content):
            if not doc or not doc.get("apiVersion", "").startswith(GROUP):
                continue
            kind, spec = doc["kind"], doc.get("spec", {})
            schema = repo.api_schema(kind)["spec"]
            for err in jsonschema.Draft7Validator(schema).iter_errors(spec):
                where = ".".join(str(x) for x in err.absolute_path) or "spec"
                p.problems.append(f"{path}: {kind} {where}: {err.message}")
            if str(spec.get("image", "")).endswith(":latest"):
                p.problems.append(f"{path}: images must be pinned; ':latest' isn't allowed.")
            size = spec.get("size", "small")
            if size in SIZES and SIZES.index(size) > SIZES.index(AGENT_LIMITS["max_size"]):
                p.problems.append(
                    f"{path}: agents can request at most '{AGENT_LIMITS['max_size']}' {kind}s. "
                    f"Ask a human to open the PR for '{size}'."
                )
            if spec.get("replicas", 0) > AGENT_LIMITS["max_replicas"]:
                p.problems.append(f"{path}: agents can request at most {AGENT_LIMITS['max_replicas']} replicas.")


def propose_webservice(
    repo: Repo,
    *,
    agent: str,
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
) -> Proposal:
    p = Proposal(team=team, name=name, golden_path="new-webservice", reason=reason, agent=agent)
    with_db = database_size is not None
    rendered = _render_dir(
        repo,
        "new-webservice/skeleton",
        dict(
            name=name, team=team, description=description, image=image, port=port,
            healthPath=health_path, size=size, replicas=replicas, expose=expose, withDatabase=with_db,
        ),
    )
    if with_db:
        rendered |= _render_dir(
            repo,
            "new-webservice/skeleton-database",
            dict(name=name, team=team, size=database_size, databaseName=database_name),
        )
    base = f"tenants/{team}/{name}"
    p.files = {f"{base}/{fn}": (_annotate(c, agent) if fn != "catalog-info.yaml" else c) for fn, c in rendered.items()}
    _validate(repo, p)
    return p


def propose_database(
    repo: Repo, *, agent: str, team: str, name: str, reason: str, size: str = "small", database_name: str = "app"
) -> Proposal:
    p = Proposal(team=team, name=name, golden_path="new-database", reason=reason, agent=agent)
    rendered = _render_dir(
        repo, "new-database/skeleton", dict(name=name, team=team, size=size, databaseName=database_name)
    )
    base = f"tenants/{team}/{name}"
    p.files = {f"{base}/{fn}": (_annotate(c, agent) if fn != "catalog-info.yaml" else c) for fn, c in rendered.items()}
    _validate(repo, p)
    return p
