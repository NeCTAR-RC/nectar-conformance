"""End-to-end CLI: exit codes and JSON output via the static source."""

import json
from pathlib import Path
import shutil

from conftest import CATALOG_DIR, CHECKS_FIXTURE, FACTS_DIR

from nectar_conformance.cli.main import main
from nectar_conformance.rules.changelog import changelog_lint
from nectar_conformance.rules.loader import load_changelog, load_definitions

# Live check runs need a checks dir (no packaged fallback); the suite's own mirror serves.
_CHECKS = str(CHECKS_FIXTURE)


def _checks_dir(tmp_path, changelog_yaml):
    # The mirrored definitions copied into a temp dir so squash/diff tests can run against a
    # small, purpose-built changelog without coupling to the real one's values.
    shutil.copytree(CHECKS_FIXTURE / "definitions", tmp_path / "definitions")
    (tmp_path / "changelog.yaml").write_text(changelog_yaml)
    return str(tmp_path)


_SQUASH_CHANGELOG = """\
tags:
  "2026.1": "2026-02-01"
entries:
  - {check_id: ovn.version, value: "24.03", effective: "2026-01-01"}
  - {check_id: ovn.version, value: "24.09", effective: "2026-03-01", due: "2026-04-01"}
  - {check_id: mariadb.version, value: "10.11", effective: "2026-01-01"}
"""

_DIFF_CHANGELOG = """\
tags:
  "2026.1": "2026-02-01"
  "2026.2": "2026-08-01"
entries:
  - {check_id: nova.compute.image_tag, value: "27.5.1", effective: "2026-01-01"}
  - {check_id: nova.compute.image_tag, value: "29.4.0", effective: "2026-06-01", due: "2026-07-01"}
"""


def test_check_run_json_reports_failure_and_exit_1(capsys):
    code = main(
        [
            "check",
            "run",
            "--site",
            "ardctest",
            "--conformance-version",
            "2026.1",
            "--checks-dir",
            _CHECKS,
            "--source",
            "static",
            "--catalog-dir",
            str(CATALOG_DIR),
            "--facts-dir",
            str(FACTS_DIR),
            "--format",
            "json",
        ]
    )
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["site"] == "ardctest"
    assert data["summary"]["result"] == "fail"
    assert code == 1  # error-severity failure at default threshold


def test_check_run_unknown_version_is_operational_error(capsys):
    code = main(
        [
            "check",
            "run",
            "--site",
            "ardctest",
            "--conformance-version",
            "1999.9",
            "--checks-dir",
            _CHECKS,
            "--source",
            "static",
            "--catalog-dir",
            str(CATALOG_DIR),
        ]
    )
    assert code == 3


def test_check_run_as_of_live_label(capsys):
    # No --conformance-version: a live run pinned to --as-of, treated as a test-tier site.
    code = main(
        [
            "check",
            "run",
            "--site",
            "ardctest",
            "--as-of",
            "2026-06-17",
            "--site-tier",
            "test",
            "--checks-dir",
            _CHECKS,
            "--source",
            "static",
            "--catalog-dir",
            str(CATALOG_DIR),
            "--facts-dir",
            str(FACTS_DIR),
            "--format",
            "json",
        ]
    )
    data = json.loads(capsys.readouterr().out)
    assert data["conformance_version"] == "(live)"
    assert data["generated_at"] == "2026-06-17T00:00:00Z"
    assert "advisory" in data["summary"]
    assert (
        code == 1
    )  # the incomplete fixture site still fails host-count checks


def test_version_list_exit_0(capsys):
    code = main(["version", "list", "--checks-dir", _CHECKS])
    out = capsys.readouterr().out
    assert "2026.1" in out
    assert code == 0


def test_version_squash_writes_baseline_and_archive(tmp_path):
    checks = _checks_dir(tmp_path, _SQUASH_CHANGELOG)
    original = (Path(checks) / "changelog.yaml").read_text()

    code = main(
        [
            "version",
            "squash",
            "--name",
            "2027.0",
            "--as-of",
            "2026-06-15",
            "--checks-dir",
            checks,
        ]
    )
    assert code == 0

    # The archive is a verbatim copy of the pre-squash changelog (history preserved).
    archive = Path(checks) / "archive" / "changelog-2027.0.yaml"
    assert archive.exists()
    assert archive.read_text() == original

    # The rewritten live log loads, lints clean, gains the new tag, and drops the
    # superseded ovn 24.03 entry (only the enforced 24.09 baseline remains).
    changelog = load_changelog(checks)
    assert "2027.0" in changelog.tags
    assert changelog_lint(changelog, load_definitions(checks)) == []
    ovn = [e for e in changelog.entries if e.check_id == "ovn.version"]
    assert len(ovn) == 1 and ovn[0].value == "24.09"


def test_version_squash_refuses_existing_name(tmp_path):
    checks = _checks_dir(tmp_path, _SQUASH_CHANGELOG)
    assert (
        main(
            [
                "version",
                "squash",
                "--name",
                "2027.0",
                "--as-of",
                "2026-06-15",
                "--checks-dir",
                checks,
            ]
        )
        == 0
    )
    # A second squash to the same version must refuse rather than clobber.
    code = main(
        [
            "version",
            "squash",
            "--name",
            "2027.0",
            "--as-of",
            "2026-06-16",
            "--checks-dir",
            checks,
        ]
    )
    assert code == 3


def test_version_squash_refuses_future_date(tmp_path):
    # The squash date is when the squash happens; a future --as-of must be rejected so it
    # cannot bake not-yet-due rollouts into the baseline.
    checks = _checks_dir(tmp_path, _SQUASH_CHANGELOG)
    code = main(
        [
            "version",
            "squash",
            "--name",
            "2099.0",
            "--as-of",
            "2099-01-01",
            "--checks-dir",
            checks,
        ]
    )
    assert code == 3


def test_version_diff_reports_value_change(tmp_path, capsys):
    checks = _checks_dir(tmp_path, _DIFF_CHANGELOG)
    code = main(
        ["version", "diff", "2026.1", "2026.2", "--checks-dir", checks]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "changed (1)" in out
    assert "nova.compute.image_tag" in out
    assert "27.5.1 -> 29.4.0" in out


def test_check_list_and_severity_filter(capsys):
    code = main(
        [
            "check",
            "list",
            "--conformance-version",
            "2026.1",
            "--checks-dir",
            _CHECKS,
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Checks for conformance 2026.1:" in out
    # The --severity branch filters the listing.
    assert (
        main(
            [
                "check",
                "list",
                "--conformance-version",
                "2026.1",
                "--checks-dir",
                _CHECKS,
                "--severity",
                "error",
            ]
        )
        == 0
    )


def test_check_list_requires_a_version(capsys):
    assert main(["check", "list"]) == 2


def test_check_list_unknown_version_is_operational_error(capsys):
    assert (
        main(
            [
                "check",
                "list",
                "--conformance-version",
                "1999.9",
                "--checks-dir",
                _CHECKS,
            ]
        )
        == 3
    )


def test_check_show_prints_definition(capsys):
    code = main(["check", "show", "rabbitmq.version", "--checks-dir", _CHECKS])
    out = capsys.readouterr().out
    assert code == 0
    assert "rabbitmq.version" in out
    assert "assertion:" in out


def test_check_show_unknown_is_operational_error(capsys):
    assert (
        main(["check", "show", "no.such.check", "--checks-dir", _CHECKS]) == 3
    )


_OLD_REPORT = {
    "results": [
        {"rule_id": "a.fix", "status": "fail", "severity": "error"},
        {"rule_id": "a.reg", "status": "pass", "severity": "warning"},
        {"rule_id": "a.same", "status": "fail", "severity": "error"},
        {"rule_id": "a.removed", "status": "fail", "severity": "info"},
    ]
}
_NEW_REPORT = {
    "results": [
        {"rule_id": "a.fix", "status": "pass", "severity": "error"},
        {"rule_id": "a.reg", "status": "fail", "severity": "warning"},
        {"rule_id": "a.same", "status": "fail", "severity": "error"},
        {"rule_id": "a.added", "status": "pass", "severity": "info"},
    ]
}


def test_report_diff_classifies_and_gates_on_regression(tmp_path, capsys):
    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text(json.dumps(_OLD_REPORT))
    new.write_text(json.dumps(_NEW_REPORT))
    code = main(["report", "diff", str(old), str(new)])
    out = capsys.readouterr().out
    assert "Fixed (1)" in out
    assert "Regressed (1)" in out
    assert "Still failing (1)" in out
    assert "Added checks (1)" in out
    assert "Removed checks (1)" in out
    assert code == 1  # a regression gates CI non-zero


def test_report_diff_unreadable_report_is_operational_error(capsys):
    assert main(["report", "diff", "/no/such/a.json", "/no/such/b.json"]) == 3


# The CI gate the nectar-conformance-checks repo runs on every change.
_BAD_CHANGELOG = """\
entries:
  - {check_id: no.such.check, value: "1", effective: "2026-01-01"}
"""


def test_changelog_lint_ok(capsys):
    code = main(["changelog", "lint", "--checks-dir", _CHECKS])
    out = capsys.readouterr().out
    assert code == 0
    assert "ok" in out


def test_changelog_lint_reports_violations(tmp_path, capsys):
    checks = _checks_dir(tmp_path, _BAD_CHANGELOG)
    code = main(["changelog", "lint", "--checks-dir", checks])
    err = capsys.readouterr().err
    assert code == 1
    assert "no.such.check" in err


def test_changelog_lint_missing_dir_is_operational_error(tmp_path):
    code = main(["changelog", "lint", "--checks-dir", str(tmp_path / "nope")])
    assert code == 3
