"""Report serialisation (JSON contract) and human rendering."""

import io
import json

from conftest import FIXTURE_TAG_DATE, VERSION, fixture_rules

from nectar_conformance.engine.runner import evaluate
from nectar_conformance.report import human
from nectar_conformance.results.model import (
    Advisory,
    CheckResult,
    REPORT_SCHEMA_VERSION,
    Report,
    RuleResult,
    Status,
)
from nectar_conformance.results.serialise import report_to_dict, report_to_json


def _report(site_model):
    rules = fixture_rules(tier="prod", as_of=FIXTURE_TAG_DATE)
    return evaluate(site_model, rules, VERSION)


def test_json_contract(site_model):
    report = _report(site_model)
    data = report_to_dict(report)
    assert data["schema_version"] == REPORT_SCHEMA_VERSION
    assert data["site"] == "ardctest"
    assert data["conformance_version"] == "2026.1"
    assert set(data["summary"]) >= {"total", "pass", "fail", "score", "result"}
    assert isinstance(data["results"], list) and data["results"]
    # Round-trips through JSON.
    assert json.loads(report_to_json(report)) == data


def test_human_render_contains_key_lines(site_model):
    report = _report(site_model)
    buf = io.StringIO()
    human.render(report, buf)
    text = buf.getvalue()
    assert "Nectar Conformance Report" in text
    assert "glance.api.image_tag" in text
    assert "Result:" in text


# --- the "At risk" treatment: passing checks whose pending change is due soon ---------


def _mk_rule(rule_id, status, advisory=None):
    check = CheckResult(
        rule_id=rule_id,
        title=rule_id,
        spec_section="s1",
        status=status,
        message="observed 'x'",
        advisory=advisory,
    )
    return RuleResult(
        rule_id=rule_id,
        title=rule_id,
        spec_section="s1",
        results=(check,),
    )


def _mk_report(*rule_results):
    return Report(
        site="ardctest",
        conformance_version="(live)",
        source="static",
        generated_at="2026-07-09T00:00:00Z",
        rule_results=tuple(rule_results),
    )


def _render(report, **kwargs):
    buf = io.StringIO()
    human.render(report, buf, **kwargs)
    return buf.getvalue()


def test_human_render_at_risk_within_window():
    soon = Advisory(
        upcoming_value="2.0", due="2026-07-19", days=10, tier="prod"
    )
    report = _mk_report(
        _mk_rule("chk.pass", Status.PASS, soon),
        # A FAIL rule can also carry an advisory (node on neither value); it already
        # fails and must not be double-reported as at risk.
        _mk_rule("chk.fail", Status.FAIL, soon),
    )
    text = _render(report)
    assert "will FAIL" in text
    assert "At risk: 1 passing check(s) will fail within 30 days" in text
    block = text.split("At risk:")[1]
    assert "chk.pass" in block
    assert "chk.fail" not in block


def test_human_render_no_at_risk_outside_window():
    far = Advisory(
        upcoming_value="2.0", due="2027-01-25", days=200, tier="prod"
    )
    report = _mk_report(_mk_rule("chk.pass", Status.PASS, far))
    text = _render(report)
    assert "Upcoming: 1 change(s) pending" in text
    assert "At risk:" not in text
    assert "will FAIL" not in text


def test_human_render_due_within_widens_window():
    far = Advisory(
        upcoming_value="2.0", due="2027-01-25", days=200, tier="prod"
    )
    report = _mk_report(_mk_rule("chk.pass", Status.PASS, far))
    text = _render(report, due_within=365)
    assert "At risk: 1 passing check(s) will fail within 365 days" in text


def test_human_render_days_none_falls_back_to_due():
    # days baked as None: derive it from the absolute due date vs the report date.
    adv = Advisory(
        upcoming_value="2.0", due="2026-07-14", days=None, tier="prod"
    )
    report = _mk_report(_mk_rule("chk.pass", Status.PASS, adv))
    text = _render(report)
    assert "At risk:" in text
    assert "in 5 day(s)" in text

    # An unparsable due date is silently not at risk (and never crashes).
    bad = Advisory(
        upcoming_value="2.0", due="not-a-date", days=None, tier="prod"
    )
    text = _render(_mk_report(_mk_rule("chk.pass", Status.PASS, bad)))
    assert "At risk:" not in text
    assert "(soon)" in text
