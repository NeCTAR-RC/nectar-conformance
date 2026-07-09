"""The read-only JSON API, driven over a fixture-populated reports directory."""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import shutil

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


def _populate(
    tmp_path, checks_dir: str = CHECKS_DIR, facts_dir: str | None = None
) -> None:
    # Populate the reports dir the way the refresh job would.
    refresh_once(
        Config(checks_dir=checks_dir),
        tier="prod",
        sites=["ardctest"],
        version=None,
        source="static",
        source_kwargs={
            "catalog_dir": str(CATALOG_DIR),
            "facts_dir": facts_dir,
            "site_repo": None,
        },
        reports_dir=tmp_path,
    )


def _serve(tmp_path, checks_dir: str = CHECKS_DIR) -> TestClient:
    settings = WebSettings(
        config=Config(checks_dir=checks_dir),
        tier="prod",
        reports_dir=tmp_path,
        static_dir=None,
    )
    return TestClient(create_app(settings))


def _fail_last_run(tmp_path, site: str, message: str) -> None:
    # Rewrite status.json as a total-failure refresh pass would leave it: errors
    # recorded, no sites evaluated, last good reports untouched on disk.
    path = tmp_path / "status.json"
    status = json.loads(path.read_text())
    status["sites"] = {}
    status["errors"] = {site: message}
    path.write_text(json.dumps(status))


@pytest.fixture
def client(tmp_path) -> TestClient:
    _populate(tmp_path)
    return _serve(tmp_path)


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["tier"] == "prod"
    assert body["sites"] >= 1
    assert body["failed_sites"] == []
    assert body["last_attempt_at"] == body["reports_generated_at"]
    # The dashboard reads its own version off /health (see frontend App.jsx).
    assert body["version"] == __version__


def test_health_degraded_when_last_refresh_failed(tmp_path):
    _populate(tmp_path)
    _fail_last_run(tmp_path, "ardctest", "PuppetDB query failed")
    client = _serve(tmp_path)
    resp = client.get("/api/health")
    # Still 200: the k8s probes hit this route and the web pod itself is fine.
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["failed_sites"] == ["ardctest"]


def test_sites_flags_stale_report_when_site_errored(tmp_path):
    _populate(tmp_path)
    _fail_last_run(tmp_path, "ardctest", "PuppetDB query failed")
    client = _serve(tmp_path)
    sites = {s["site"]: s for s in client.get("/api/sites").json()["sites"]}
    entry = sites["ardctest"]
    # The last good report is still served, now flagged with the failure.
    assert entry["error"] == "PuppetDB query failed"
    assert entry["summary"]["total"] > 0


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


_ZERO_ROLLOUT = {
    "overdue": [],
    "pending": [],
    "adopted": [],
    "counts": {"overdue": 0, "pending": 0, "due_soon": 0, "adopted": 0},
    "next_due": None,
}


def _checks_with_dated_change(dest: Path) -> str:
    # A purpose-built checks dir: the mirrored definitions plus a changelog whose dated
    # entries straddle the real wall clock (the /sites endpoint judges at date.today()).
    # The fixture site observes ubuntu 24.04 on its database and mq nodes, so the
    # upcoming ["26.04"] database value is pending (due in 10 days) while the narrowed
    # ["24.04"] mq value is already adopted (due in 20 days, still in flight).
    today = date.today()
    baseline_effective = (today - timedelta(days=100)).isoformat()
    effective = (today - timedelta(days=10)).isoformat()
    due = (today + timedelta(days=10)).isoformat()
    mq_due = (today + timedelta(days=20)).isoformat()
    shutil.copytree(Path(CHECKS_DIR) / "definitions", dest / "definitions")
    (dest / "changelog.yaml").write_text(
        "entries:\n"
        "  - {check_id: os.database.ubuntu, "
        f'value: ["24.04", "22.04"], effective: "{baseline_effective}"}}\n'
        "  - {check_id: os.database.ubuntu, "
        f'value: ["26.04"], effective: "{effective}", due: "{due}"}}\n'
        "  - {check_id: os.mq.ubuntu, "
        f'value: ["24.04", "22.04"], effective: "{baseline_effective}"}}\n'
        "  - {check_id: os.mq.ubuntu, "
        f'value: ["24.04"], effective: "{effective}", due: "{mq_due}"}}\n'
    )
    return str(dest)


def test_sites_rollout_zero_with_baseline_changelog(client):
    # The frozen fixture changelog has no dated entries, so every report-bearing site
    # reports the explicit zero shape ("up to date"), distinct from null ("no data").
    body = client.get("/api/sites").json()
    assert body["within"] == 30
    assert body["as_of"] == date.today().isoformat()
    entry = {s["site"]: s for s in body["sites"]}["ardctest"]
    assert entry["rollout"] == _ZERO_ROLLOUT


def test_sites_rollout_with_dated_change(tmp_path):
    checks = _checks_with_dated_change(tmp_path / "checks")
    reports = tmp_path / "reports"
    reports.mkdir()
    # The OS check reads a fact, so this run needs the fixture facts.
    _populate(reports, checks_dir=checks, facts_dir=str(FIXTURES / "facts"))
    client = _serve(reports, checks_dir=checks)

    body = client.get("/api/sites").json()
    view = {s["site"]: s for s in body["sites"]}["ardctest"]["rollout"]
    assert view["counts"] == {
        "overdue": 0,
        "pending": 1,
        "due_soon": 1,
        "adopted": 1,
    }
    ref = view["pending"][0]
    assert ref["check_id"] == "os.database.ubuntu"
    assert ref["target"] == ["26.04"]
    assert ref["days"] in (
        9,
        10,
        11,
    )  # tolerant of a midnight rollover mid-test
    assert view["next_due"] == ref["due"]
    # The already-adopted (still in-flight) mq change is carried with its status.
    assert [r["check_id"] for r in view["adopted"]] == ["os.mq.ubuntu"]

    # Narrowing the window demotes it from due-soon; it stays pending.
    narrow = client.get("/api/sites", params={"within": 5}).json()
    view = {s["site"]: s for s in narrow["sites"]}["ardctest"]["rollout"]
    assert view["counts"] == {
        "overdue": 0,
        "pending": 1,
        "due_soon": 0,
        "adopted": 1,
    }
    assert narrow["within"] == 5


def test_sites_within_param_validation(client):
    for bad in ("-1", "999", "abc"):
        assert (
            client.get("/api/sites", params={"within": bad}).status_code == 422
        )


def test_sites_error_only_row_has_null_rollout(tmp_path):
    # A site that errored and has no report cannot be judged: rollout is null, while
    # report-bearing sites still carry the explicit shape.
    _populate(tmp_path)
    _fail_last_run(tmp_path, "ghost", "PuppetDB query failed")
    client = _serve(tmp_path)
    sites = {s["site"]: s for s in client.get("/api/sites").json()["sites"]}
    assert sites["ghost"]["rollout"] is None
    assert sites["ardctest"]["rollout"] == _ZERO_ROLLOUT


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
