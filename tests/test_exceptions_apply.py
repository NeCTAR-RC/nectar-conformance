"""apply_exceptions: the pure Report -> Report transform."""

from datetime import date

from nectar_conformance.results.exceptions import apply_exceptions
from nectar_conformance.results.model import (
    CheckResult,
    Report,
    RuleResult,
    Status,
)
from nectar_conformance.rules.exceptions import ExceptionEntry

AS_OF = date(2026, 6, 15)


def _check(rule_id, node, status):
    return CheckResult(
        rule_id=rule_id,
        title=rule_id,
        spec_section="Compute Node",
        status=status,
        message=f"observed 'Y' on {node}" if node else "site-level",
        node=node,
        observed="Y",
        expected=["N", "0"],
    )


def _report(*rule_results, site="ardctest"):
    return Report(
        site=site,
        conformance_version="(live)",
        source="static",
        generated_at="2026-06-15T00:00:00Z",
        rule_results=tuple(rule_results),
    )


def _nested_virt_rule(*checks):
    return RuleResult(
        rule_id="nova.compute.nested_virt.intel",
        title="Nested virtualisation is disabled on Intel compute nodes",
        spec_section="Compute Node",
        results=tuple(checks),
    )


def _entry(**kwargs):
    base = dict(
        check_id="nova.compute.nested_virt.intel",
        site="ardctest",
        hosts=frozenset({"cc2.example.test", "cc3.example.test"}),
        reason="nested virt sanctioned on these hypervisors",
        expiry="2027-01-01",
    )
    base.update(kwargs)
    return ExceptionEntry(**base)


def test_active_exception_downgrades_fail_to_excepted():
    rule_id = "nova.compute.nested_virt.intel"
    report = _report(
        _nested_virt_rule(
            _check(rule_id, "cc1.example.test", Status.PASS),
            _check(rule_id, "cc2.example.test", Status.FAIL),
            _check(rule_id, "cc3.example.test", Status.FAIL),
        )
    )
    out = apply_exceptions(report, [_entry()], as_of=AS_OF)
    statuses = {c.node: c.status for c in out.rule_results[0].results}
    assert statuses["cc1.example.test"] is Status.PASS
    assert statuses["cc2.example.test"] is Status.EXCEPTED
    assert statuses["cc3.example.test"] is Status.EXCEPTED
    # All failures waived: the rule no longer counts as failing.
    assert out.rule_results[0].status is Status.EXCEPTED
    assert not out.has_failures
    assert out.summary["excepted"] == 1
    excepted = out.rule_results[0].results[1]
    assert excepted.exception is not None
    assert not excepted.exception.expired
    assert excepted.exception.reason.startswith("nested virt")


def test_unwaived_host_keeps_rule_failing():
    rule_id = "nova.compute.nested_virt.intel"
    report = _report(
        _nested_virt_rule(
            _check(rule_id, "cc2.example.test", Status.FAIL),
            _check(rule_id, "cc4.example.test", Status.FAIL),  # not granted
        )
    )
    out = apply_exceptions(report, [_entry()], as_of=AS_OF)
    assert out.rule_results[0].status is Status.FAIL
    assert out.has_failures


def test_rollup_prefers_excepted_over_pass():
    rule_id = "nova.compute.nested_virt.intel"
    report = _report(
        _nested_virt_rule(
            _check(rule_id, "cc1.example.test", Status.PASS),
            _check(rule_id, "cc2.example.test", Status.FAIL),
        )
    )
    out = apply_exceptions(report, [_entry()], as_of=AS_OF)
    # One pass + one excepted: the live waiver stays visible at rule level.
    assert out.rule_results[0].status is Status.EXCEPTED


def test_expired_exception_annotates_but_still_fails():
    rule_id = "nova.compute.nested_virt.intel"
    report = _report(
        _nested_virt_rule(_check(rule_id, "cc2.example.test", Status.FAIL))
    )
    out = apply_exceptions(report, [_entry(expiry="2026-06-01")], as_of=AS_OF)
    result = out.rule_results[0].results[0]
    assert result.status is Status.FAIL
    assert result.exception is not None and result.exception.expired
    assert out.has_failures


def test_not_yet_effective_exception_is_ignored():
    rule_id = "nova.compute.nested_virt.intel"
    report = _report(
        _nested_virt_rule(_check(rule_id, "cc2.example.test", Status.FAIL))
    )
    out = apply_exceptions(
        report, [_entry(effective="2026-07-01")], as_of=AS_OF
    )
    result = out.rule_results[0].results[0]
    assert result.status is Status.FAIL
    assert result.exception is None  # pending: no suppression, no annotation


def test_other_site_check_and_pass_results_untouched():
    rule_id = "nova.compute.nested_virt.intel"
    report = _report(
        _nested_virt_rule(_check(rule_id, "cc2.example.test", Status.FAIL)),
        site="qh2",
    )
    out = apply_exceptions(report, [_entry()], as_of=AS_OF)
    assert out is report  # no entries for this site: identity

    report = _report(
        _nested_virt_rule(_check(rule_id, "cc2.example.test", Status.FAIL))
    )
    other_check = _entry(check_id="glance.api.image_tag")
    out = apply_exceptions(report, [other_check], as_of=AS_OF)
    assert out.rule_results[0].results[0].status is Status.FAIL
    assert out.rule_results[0].results[0].exception is None


def test_no_exceptions_is_identity():
    report = _report(
        _nested_virt_rule(
            _check(
                "nova.compute.nested_virt.intel",
                "cc2.example.test",
                Status.FAIL,
            )
        )
    )
    assert apply_exceptions(report, [], as_of=AS_OF) is report


def test_excepted_excluded_from_score_like_skip():
    rule_id = "nova.compute.nested_virt.intel"
    passing = RuleResult(
        rule_id="glance.api.image_tag",
        title="t",
        spec_section="s",
        results=(
            _check("glance.api.image_tag", "oc1.example.test", Status.PASS),
        ),
    )
    report = _report(
        _nested_virt_rule(_check(rule_id, "cc2.example.test", Status.FAIL)),
        passing,
    )
    assert report.score == 0.5
    out = apply_exceptions(report, [_entry()], as_of=AS_OF)
    # The excepted rule leaves the denominator entirely.
    assert out.score == 1.0
    assert out.summary["result"] == "pass"
