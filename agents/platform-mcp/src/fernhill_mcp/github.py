"""The server's only write path: open a pull request (ADR-0001, ADR-0012).

Identity, in order of preference:
  1. GitHub App (GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY[_PATH] +
     GITHUB_APP_INSTALLATION_ID). PRs are authored by `<app>[bot]`, a
     distinct, auditable identity with only contents + pull-requests access.
  2. GITHUB_TOKEN. Works, but PRs appear as the token's owner, so the agent
     is only distinguishable by label and annotation. Development only.
  3. Neither: dry run. Proposals are returned, nothing is written.

Even with write access to contents, the agent can't change main: branch
protection requires a PR and a CODEOWNER review.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx
import jwt

API = "https://api.github.com"
AGENT_LABEL = "agent-authored"


@dataclass
class Identity:
    kind: str  # "app" | "token" | "none"
    token: str | None = None


def identity_from_env() -> Identity:
    app_id = os.environ.get("GITHUB_APP_ID")
    installation = os.environ.get("GITHUB_APP_INSTALLATION_ID")
    key = os.environ.get("GITHUB_APP_PRIVATE_KEY")
    if not key and (key_path := os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH")):
        key = open(os.path.expanduser(key_path)).read()
    if app_id and installation and key:
        return Identity("app", _installation_token(app_id, installation, key))
    if token := os.environ.get("GITHUB_TOKEN"):
        return Identity("token", token)
    return Identity("none")


def _installation_token(app_id: str, installation_id: str, private_key: str) -> str:
    now = int(time.time())
    assertion = jwt.encode({"iat": now - 60, "exp": now + 540, "iss": app_id}, private_key, algorithm="RS256")
    r = httpx.post(
        f"{API}/app/installations/{installation_id}/access_tokens",
        headers={"Authorization": f"Bearer {assertion}", "Accept": "application/vnd.github+json"},
        # Narrower than the App's own grant: this token can only touch the
        # one repo: write contents, PRs and labels, read check results.
        json={"permissions": {"contents": "write", "pull_requests": "write", "issues": "write", "checks": "read"}},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["token"]


class GitHub:
    def __init__(self, token: str, repo: str, client: httpx.Client | None = None):
        self.repo = repo
        self.http = client or httpx.Client(
            base_url=API,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=30,
        )

    def _req(self, method: str, path: str, **kw) -> dict | list:
        r = self.http.request(method, f"/repos/{self.repo}{path}", **kw)
        r.raise_for_status()
        return r.json() if r.content else {}

    def open_pull_request(
        self, *, base: str, branch: str, files: dict[str, str], title: str, body: str, commit_message: str
    ) -> dict:
        """One commit with all files on a new branch, then a labelled PR."""
        base_sha = self._req("GET", f"/git/ref/heads/{base}")["object"]["sha"]
        base_tree = self._req("GET", f"/git/commits/{base_sha}")["tree"]["sha"]
        tree = self._req(
            "POST",
            "/git/trees",
            json={
                "base_tree": base_tree,
                "tree": [{"path": p, "mode": "100644", "type": "blob", "content": c} for p, c in sorted(files.items())],
            },
        )
        commit = self._req(
            "POST", "/git/commits", json={"message": commit_message, "tree": tree["sha"], "parents": [base_sha]}
        )
        self._req("POST", "/git/refs", json={"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
        pr = self._req("POST", "/pulls", json={"title": title, "head": branch, "base": base, "body": body})
        self._req("POST", f"/issues/{pr['number']}/labels", json={"labels": [AGENT_LABEL]})
        return {"number": pr["number"], "url": pr["html_url"], "branch": branch, "commit": commit["sha"]}

    def pull_request_status(self, number: int) -> dict:
        """What an agent needs to iterate: CI results, review state, merge state."""
        pr = self._req("GET", f"/pulls/{number}")
        runs = self._req("GET", f"/commits/{pr['head']['sha']}/check-runs")["check_runs"]
        reviews = self._req("GET", f"/pulls/{number}/reviews")
        return {
            "number": number,
            "url": pr["html_url"],
            "state": "merged" if pr.get("merged") else pr["state"],
            "checks": [
                {"name": r["name"], "status": r["status"], "conclusion": r["conclusion"], "details": r["html_url"]}
                for r in runs
            ],
            "reviews": [{"by": rv["user"]["login"], "state": rv["state"], "body": rv["body"]} for rv in reviews],
        }
