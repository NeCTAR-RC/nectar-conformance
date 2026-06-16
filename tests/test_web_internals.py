"""Unit tests for the web store, serialiser and settings."""

from __future__ import annotations

import json
from pathlib import Path

from nectar_conformance.config import Config
from nectar_conformance.web import settings as settings_mod
from nectar_conformance.web.serialise import (
    rule_to_dict,
    site_summary,
    worst_failing_severity,
)
from nectar_conformance.web.settings import load_settings
from nectar_conformance.web.store import ReportStore


def test_store_empty_dir(tmp_path):
    store = ReportStore(tmp_path)
    assert store.site_ids() == []
    assert store.all_reports() == {}
    assert store.get_report("nope") is None
    status = store.status()
    assert status["generated_at"] is None and status["sites"] == {}


def test_store_reads_and_caches(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "site1.json").write_text(json.dumps({"site": "site1"}))
    (tmp_path / "status.json").write_text(json.dumps({"tier": "prod"}))
    store = ReportStore(tmp_path)
    assert store.site_ids() == ["site1"]
    report = store.get_report("site1")
    assert report is not None and report["site"] == "site1"
    # Second read hits the mtime cache (same object).
    assert store.get_report("site1") is store.get_report("site1")
    assert store.status()["tier"] == "prod"
    assert store.status() is store.status()


def test_worst_failing_severity_and_summary():
    report = {
        "summary": {"score": 0.5, "result": "fail"},
        "generated_at": "t",
        "conformance_version": "2026.1",
        "results": [
            {"status": "fail", "severity": "warning"},
            {"status": "fail", "severity": "error"},
            {"status": "pass", "severity": "error"},
        ],
    }
    assert worst_failing_severity(report) == "error"
    assert worst_failing_severity({"results": []}) is None
    summ = site_summary("site1", report)
    assert summ["site"] == "site1"
    assert summ["worst_severity"] == "error"
    assert summ["error"] is None


class _Rule:
    id = "x.y"
    title = "X"
    spec_section = None
    severity = "error"
    expected = "1.0"
    optional = False
    due = None
    has_pending = False
    pending_value = None
    pending_due = None
    pending_days = None
    remediation = None


def test_rule_to_dict_without_remediation():
    out = rule_to_dict(_Rule())
    assert out["id"] == "x.y"
    assert out["expected"] == "1.0"
    assert out["remediation"] is None


def test_load_settings_ignores_missing_static_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("NECTAR_CONFORMANCE_WEB_STATIC", raising=False)
    s = load_settings(
        tier="test",
        reports_dir=str(tmp_path),
        static_dir=str(tmp_path / "does-not-exist"),
    )
    assert s.tier == "test"
    assert s.static_dir is None  # a non-directory is dropped
    assert isinstance(s.config, Config)


def test_packaged_static_helper_returns_none_or_dir():
    # Exercises the helper; the packaged static dir is absent in a source checkout.
    result = settings_mod._packaged_static()
    assert result is None or isinstance(result, Path)
