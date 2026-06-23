"""The read-only JSON API, driven over a fixture-populated reports directory."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from nectar_conformance import __version__
from nectar_conformance.config import Config
from nectar_conformance.web.app import create_app
from nectar_conformance.web.refresh import refresh_once
from nectar_conformance.web.settings import WebSettings

FIXTURES = Path(__file__).parent / "fixtures"
CATALOG_DIR = FIXTURES / "catalogs"
# The refresh job and the changelog API endpoints both need a checks dir (no packaged
# fallback); the suite's own mirror serves.
CHECKS_DIR = str(FIXTURES / "checks")


@pytest.fixture
def client(tmp_path) -> TestClient:
    # Populate the reports dir the way the refresh job would, then serve it.
    refresh_once(
        Config(checks_dir=CHECKS_DIR),
        tier="prod",
        sites=["ardctest"],
        version=None,
        source="static",
        source_kwargs={
            "catalog_dir": str(CATALOG_DIR),
            "facts_dir": None,
            "site_repo": None,
        },
        reports_dir=tmp_path,
    )
    settings = WebSettings(
        config=Config(checks_dir=CHECKS_DIR),
        tier="prod",
        reports_dir=tmp_path,
        static_dir=None,
    )
    return TestClient(create_app(settings))


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["tier"] == "prod"
    assert body["sites"] >= 1
    # The dashboard reads its own version off /health (see frontend App.jsx).
    assert body["version"] == __version__


def test_sites_lists_each_site_with_summary(client):
    body = client.get("/api/sites").json()
    assert body["tier"] == "prod"
    sites = {s["site"]: s for s in body["sites"]}
    assert "ardctest" in sites
    assert sites["ardctest"]["summary"]["total"] > 0


def test_site_detail_and_404(client):
    detail = client.get("/api/sites/ardctest").json()
    assert detail["site"] == "ardctest"
    assert detail["results"]
    assert client.get("/api/sites/nope").status_code == 404


def test_check_detail_across_sites(client):
    body = client.get("/api/checks/rabbitmq.version").json()
    assert body["check_id"] == "rabbitmq.version"
    assert body["title"]
    sites = {s["site"]: s for s in body["sites"]}
    assert "ardctest" in sites
    assert sites["ardctest"]["status"] in (
        "pass",
        "fail",
        "skip",
        "unknown",
        "absent",
    )
    assert client.get("/api/checks/no.such.check").status_code == 404


def test_versions_and_requirements(client):
    versions = client.get("/api/versions").json()["versions"]
    names = {v["name"] for v in versions}
    assert "2026.1" in names

    reqs = client.get("/api/versions/2026.1/requirements").json()
    assert reqs["version"] == "2026.1"
    assert reqs["requirements"]
    sample = reqs["requirements"][0]
    assert {"id", "expected", "severity"}.issubset(sample)

    assert client.get("/api/versions/9999.9/requirements").status_code == 404


def test_versions_diff_identity(client):
    body = client.get(
        "/api/versions/diff", params={"from": "2026.1", "to": "2026.1"}
    ).json()
    assert body["changed"] == []
    assert body["added"] == []


def test_changes_pending_and_rollout_shape(client):
    body = client.get("/api/changes").json()
    changes = body["changes"]
    assert isinstance(changes, list) and changes
    # This is a prod deployment: test-only directives must not leak into its timeline.
    assert all(c["tier"] in ("all", "prod") for c in changes)

    pending = client.get("/api/changes/pending").json()
    assert pending["tier"] == "prod"
    assert isinstance(pending["pending"], list)

    rollout = client.get("/api/changes/rollout").json()
    assert rollout["tier"] == "prod"
    assert isinstance(rollout["rollout"], list)
    for entry in rollout["rollout"]:
        assert set(entry["buckets"]) == {
            "adopted",
            "pending",
            "overdue",
            "not_applicable",
        }
