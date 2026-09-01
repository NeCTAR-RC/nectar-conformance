"""run_check wiring: exceptions from the checks dir are applied to the report."""

import shutil

from conftest import CATALOG_DIR, CHECKS_FIXTURE, FACTS_DIR

from nectar_conformance.config import Config
from nectar_conformance.results.model import Status
from nectar_conformance.service import list_exceptions, run_check

# The static catalog fixture pins an old glance tag on oc2, so glance.api.image_tag
# FAILs there (proven by test_static_source.py); an exception granting exactly that
# host flips it to EXCEPTED end-to-end.
_EXCEPTIONS = """\
exceptions:
  - check_id: glance.api.image_tag
    site: ardctest
    hosts: [oc2.example.test]
    reason: "old glance pinned while the image build is fixed"
    effective: "2026-01-01"
    expiry: "2099-01-01"
"""


def _checks_dir(tmp_path, exceptions_yaml=None):
    shutil.copytree(CHECKS_FIXTURE / "definitions", tmp_path / "definitions")
    shutil.copy(CHECKS_FIXTURE / "changelog.yaml", tmp_path / "changelog.yaml")
    if exceptions_yaml is not None:
        (tmp_path / "exceptions.yaml").write_text(exceptions_yaml)
    return str(tmp_path)


def _run(checks_dir):
    return run_check(
        Config(checks_dir=checks_dir),
        "ardctest",
        "2026.1",
        source="static",
        source_kwargs={
            "catalog_dir": str(CATALOG_DIR),
            "facts_dir": str(FACTS_DIR),
        },
    )


def test_run_check_applies_exceptions(tmp_path):
    report = _run(_checks_dir(tmp_path, _EXCEPTIONS))
    statuses = {rr.rule_id: rr.status for rr in report.rule_results}
    assert statuses["glance.api.image_tag"] is Status.EXCEPTED
    excepted = next(
        c
        for rr in report.rule_results
        if rr.rule_id == "glance.api.image_tag"
        for c in rr.results
        if c.status is Status.EXCEPTED
    )
    assert excepted.node == "oc2.example.test"
    assert excepted.exception is not None
    assert excepted.exception.reason.startswith("old glance pinned")


def test_run_check_without_exceptions_file_is_unchanged(tmp_path):
    report = _run(_checks_dir(tmp_path))
    statuses = {rr.rule_id: rr.status for rr in report.rule_results}
    assert statuses["glance.api.image_tag"] is Status.FAIL


def test_list_exceptions_reports_state(tmp_path):
    checks = _checks_dir(tmp_path, _EXCEPTIONS)
    cfg = Config(checks_dir=checks)
    entries = list_exceptions(cfg, as_of="2026-06-15")
    assert len(entries) == 1
    e = entries[0]
    assert e["state"] == "active"
    assert e["hosts"] == ["oc2.example.test"]

    assert list_exceptions(cfg, site="qh2") == []
    expired = list_exceptions(cfg, as_of="2099-06-15")
    assert expired[0]["state"] == "expired"
