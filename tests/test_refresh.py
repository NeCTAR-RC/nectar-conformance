"""The refresh command publishes per-site reports + a status file."""

from __future__ import annotations

import json
from pathlib import Path

from nectar_conformance.config import Config
from nectar_conformance.errors import SiteNotFoundError
from nectar_conformance.results.model import Report
from nectar_conformance.web import refresh as refresh_mod
from nectar_conformance.web.refresh import refresh_once

FIXTURES = Path(__file__).parent / "fixtures"
CATALOG_DIR = FIXTURES / "catalogs"
# Checks now live outside the package; a real run needs a checks dir (the suite's mirror).
CHECKS_DIR = str(FIXTURES / "checks")


def _fake_report(site: str) -> Report:
    return Report(
        site=site,
        conformance_version="v",
        source="test",
        generated_at="2026-06-17T00:00:00Z",
    )


def test_refresh_static_writes_report_and_status(tmp_path):
    status = refresh_once(
        Config(checks_dir=CHECKS_DIR),
        tier="test",
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
    report = json.loads((tmp_path / "reports" / "ardctest.json").read_text())
    assert report["site"] == "ardctest"
    assert report["schema_version"]  # a real serialised report
    saved_status = json.loads((tmp_path / "status.json").read_text())
    assert saved_status["tier"] == "test"
    assert "ardctest" in saved_status["sites"]
    assert status["errors"] == {}
    # No half-written temp files left behind (atomic writes).
    assert not list((tmp_path / "reports").glob(".*"))


def test_refresh_records_errors_and_keeps_going(monkeypatch, tmp_path):
    def fake(config, *, site, version, source, source_kwargs, as_of, tier):
        if site == "bad":
            raise SiteNotFoundError("no nodes")
        return _fake_report(site)

    monkeypatch.setattr(refresh_mod, "run_check", fake)
    status = refresh_once(
        Config(),
        tier="prod",
        sites=["good", "bad"],
        version=None,
        source=None,
        source_kwargs=None,
        reports_dir=tmp_path,
    )
    assert "good" in status["sites"]
    assert status["errors"]["bad"] == "no nodes"
    assert (tmp_path / "reports" / "good.json").is_file()
    assert not (tmp_path / "reports" / "bad.json").exists()


def test_refresh_main_static(tmp_path):
    rc = refresh_mod.main(
        [
            "--source",
            "static",
            "--site",
            "ardctest",
            "--catalog-dir",
            str(CATALOG_DIR),
            "--checks-dir",
            CHECKS_DIR,
            "--reports-dir",
            str(tmp_path),
            "--tier",
            "test",
        ]
    )
    assert rc == 0
    assert (tmp_path / "reports" / "ardctest.json").is_file()


def test_refresh_main_static_without_site_errors(tmp_path):
    # Discovery needs PuppetDB; the static source must be given explicit --site.
    rc = refresh_mod.main(
        ["--source", "static", "--reports-dir", str(tmp_path)]
    )
    assert rc == 2


def test_refresh_main_puppetdb_discovers(monkeypatch, tmp_path):
    monkeypatch.setattr(
        refresh_mod,
        "discover_sites",
        lambda config, tier: [{"site": "x", "environment": "x"}],
    )
    monkeypatch.setattr(
        refresh_mod, "run_check", lambda *a, site, **k: _fake_report(site)
    )
    rc = refresh_mod.main(["--reports-dir", str(tmp_path), "--tier", "prod"])
    assert rc == 0
    assert (tmp_path / "reports" / "x.json").is_file()


def test_refresh_prunes_reports_for_vanished_sites(monkeypatch, tmp_path):
    monkeypatch.setattr(
        refresh_mod, "run_check", lambda *a, site, **k: _fake_report(site)
    )
    reports_subdir = tmp_path / "reports"
    reports_subdir.mkdir(parents=True)
    (reports_subdir / "old.json").write_text("{}")
    refresh_once(
        Config(),
        tier="prod",
        sites=["keep"],
        version=None,
        source=None,
        source_kwargs=None,
        reports_dir=tmp_path,
    )
    assert (reports_subdir / "keep.json").is_file()
    assert not (reports_subdir / "old.json").exists()
