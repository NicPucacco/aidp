"""The local EnvironmentConfig fixture used by render tests and the tenant
gate must be exactly what platform/apps renders with default values, or the
tests would pass against an environment no cluster has."""

import pathlib
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_local_fixture_matches_the_chart_default():
    rendered = subprocess.run(
        ["helm", "template", str(ROOT / "platform" / "apps"), "-s", "templates/environment.yaml"],
        check=True, capture_output=True, text=True,
    ).stdout
    chart = yaml.safe_load(rendered)
    fixture = yaml.safe_load((ROOT / "scripts" / "fixtures" / "environment-local.yaml").read_text())

    assert fixture["kind"] == chart["kind"] == "EnvironmentConfig"
    assert fixture["metadata"]["name"] == chart["metadata"]["name"]
    assert fixture["data"] == chart["data"]
