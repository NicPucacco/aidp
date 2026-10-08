#!/usr/bin/env python3
"""Extra rules for pull requests opened by agents (ADR-0013).

An agent PR is one authored by a known agent identity (AGENT_AUTHORS), or
labelled `agent-authored`, or on an `agent/` branch. For those:

  1. Only tenants/** may change. Agents never touch platform code, policy, CI.
  2. Every platform object changed carries platform.fernhill.io/requested-by:
     agent:<name>, so admission applies agent limits to it (agent-limits.yaml).
  3. The PR explains itself: a non-trivial "## Why" section.
  4. It's visibly labelled `agent-authored`, so reviewers know what they're reviewing.

Human PRs pass through untouched. Reads the GitHub event from
GITHUB_EVENT_PATH and diffs base...head with git.

Usage: scripts/check-agent-pr.py
"""

import json
import os
import pathlib
import re
import subprocess
import sys

import yaml

GROUP = "platform.fernhill.io"
REQUESTED_BY = f"{GROUP}/requested-by"
LABEL = "agent-authored"
AGENT_AUTHORS = {a.strip() for a in os.environ.get("AGENT_AUTHORS", "aidp-agent[bot]").split(",") if a.strip()}


def is_agent_pr(pr: dict) -> tuple[bool, str]:
    labels = {lbl["name"] for lbl in pr.get("labels", [])}
    if pr["user"]["login"] in AGENT_AUTHORS:
        return True, f"author {pr['user']['login']}"
    if LABEL in labels:
        return True, f"label {LABEL}"
    if pr["head"]["ref"].startswith("agent/"):
        return True, f"branch {pr['head']['ref']}"
    return False, ""


def check(pr: dict, changed: list[str], read) -> list[str]:
    problems = []
    outside = [f for f in changed if not f.startswith("tenants/")]
    if outside:
        problems.append("Agents may only change tenants/**. Also changed: " + ", ".join(outside))

    for path in changed:
        if not path.startswith("tenants/") or not path.endswith((".yaml", ".yml")) or path.endswith("catalog-info.yaml"):
            continue
        content = read(path)
        if content is None:  # deleted
            continue
        for doc in yaml.safe_load_all(content):
            if doc and doc.get("apiVersion", "").startswith(GROUP):
                who = (doc.get("metadata", {}).get("annotations") or {}).get(REQUESTED_BY, "")
                if not who.startswith("agent:"):
                    problems.append(
                        f"{path}: {doc['kind']} {doc['metadata']['name']} lacks {REQUESTED_BY}: agent:<name>, "
                        "so agent limits wouldn't apply at admission."
                    )

    why = re.search(r"^##\s*Why\s*$(.*?)(?=^##\s|\Z)", pr.get("body") or "", re.M | re.S)
    if not why or len(why.group(1).strip()) < 20:
        problems.append("The PR description needs a '## Why' section explaining the request.")

    if LABEL not in {lbl["name"] for lbl in pr.get("labels", [])}:
        problems.append(f"Agent PRs must carry the '{LABEL}' label.")
    return problems


def main() -> int:
    event = json.loads(pathlib.Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    pr = event.get("pull_request")
    if not pr:
        print("Not a pull request; nothing to check.")
        return 0
    agent, why = is_agent_pr(pr)
    if not agent:
        print(f"Human PR by {pr['user']['login']}; agent rules don't apply.")
        return 0

    base, head = pr["base"]["sha"], pr["head"]["sha"]
    changed = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"], check=True, capture_output=True, text=True
    ).stdout.split()

    def read(path):
        proc = subprocess.run(["git", "show", f"{head}:{path}"], capture_output=True, text=True)
        return proc.stdout if proc.returncode == 0 else None

    print(f"Agent PR ({why}); checking {len(changed)} changed file(s).")
    problems = check(pr, changed, read)
    for p in problems:
        print(f"  ✗ {p}")
    if not problems:
        print("  ✓ tenants/** only, objects stamped as agent-requested, reason given, labelled")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
