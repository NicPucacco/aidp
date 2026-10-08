import pathlib

import pytest

from fernhill_mcp.repo import Repo

ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture
def repo() -> Repo:
    return Repo(ROOT)


@pytest.fixture(autouse=True)
def no_github_credentials(monkeypatch):
    # Tests must never open real PRs.
    for var in ("GITHUB_TOKEN", "GITHUB_APP_ID", "GITHUB_APP_INSTALLATION_ID", "GITHUB_APP_PRIVATE_KEY", "GITHUB_APP_PRIVATE_KEY_PATH"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def anyio_backend():
    return "asyncio"
