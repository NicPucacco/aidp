#!/usr/bin/env python3
"""Run MCP-server proposals through the real tenant gate (ADR-0013).

1. Proposals the server would open must pass CI exactly like human changes.
2. A misbehaving agent that skips the server's own checks and pushes a
   'large' database directly must still be stopped by CI. The server's
   limits are UX; the policy is the control.

Usage: scripts/test-agent-proposals.py   (needs fernhill-platform-mcp installed)
"""

import pathlib
import subprocess
import sys
import tempfile

from fernhill_mcp import proposals as P
from fernhill_mcp.repo import Repo

ROOT = pathlib.Path(__file__).resolve().parent.parent
REASON = "Exercising the agent path end to end in CI (scripts/test-agent-proposals.py)."


def write(tmp: pathlib.Path, proposal: P.Proposal) -> None:
    for rel, content in proposal.files.items():
        path = tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def gate(tenants: pathlib.Path) -> int:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check-tenants.py"), "--tenants", str(tenants)],
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    repo = Repo(ROOT)
    failures = []

    with tempfile.TemporaryDirectory() as tmp:
        good = pathlib.Path(tmp)
        for p in (
            P.propose_webservice(repo, agent="ci", team="routing", name="route-planner",
                                 image="ghcr.io/stefanprodan/podinfo:6.15.0", port=9898,
                                 health_path="/readyz", reason=REASON, database_size="small"),
            P.propose_database(repo, agent="ci", team="tracking", name="tracking-events", reason=REASON, size="medium"),
        ):
            assert p.ok, p.problems
            write(good / "tenants", p)
        code = gate(good / "tenants")
        print(f"{'✓' if code == 0 else '✗'} server proposals pass the tenant gate")
        if code != 0:
            failures.append("server proposals")

    with tempfile.TemporaryDirectory() as tmp:
        bad = pathlib.Path(tmp)
        rogue = P.propose_database(repo, agent="rogue", team="tracking", name="huge-db", reason=REASON, size="large")
        assert not rogue.ok  # the server would refuse ...
        write(bad / "tenants", rogue)  # ... so pretend the agent pushed it anyway
        code = gate(bad / "tenants")
        print(f"{'✓' if code != 0 else '✗'} an agent-annotated 'large' database pushed directly is rejected")
        if code == 0:
            failures.append("rogue large database")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
