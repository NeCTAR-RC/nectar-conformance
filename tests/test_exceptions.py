"""Exception entries: parsing, the active window, matching, and lint."""

from datetime import date

from conftest import fixture_definitions

from nectar_conformance.rules.exceptions import (
    ExceptionEntry,
    exceptions_from_dict,
    exceptions_lint,
    is_active,
    is_expired,
    matches,
    state,
)


def _entry(**kwargs):
    base = dict(
        check_id="glance.api.image_tag",
        site="ardctest",
        hosts=frozenset({"oc2.example.test"}),
        reason="waiver",
    )
    base.update(kwargs)
    return ExceptionEntry(**base)


def test_from_dict_defaults():
    entries = exceptions_from_dict(
        {
            "exceptions": [
                {
                    "check_id": "glance.api.image_tag",
                    "site": "ardctest",
                    "hosts": ["oc2.example.test"],
                    "reason": "waiver",
                }
            ]
        }
    )
    assert len(entries) == 1
    e = entries[0]
    assert e.hosts == frozenset({"oc2.example.test"})
    assert e.effective is None and e.expiry is None and e.note is None


def test_active_window_is_effective_inclusive_expiry_exclusive():
    e = _entry(effective="2026-06-01", expiry="2026-07-01")
    assert not is_active(e, date(2026, 5, 31))  # not yet effective
    assert state(e, date(2026, 5, 31)) == "pending"
    assert is_active(e, date(2026, 6, 1))  # active on and from effective
    assert is_active(e, date(2026, 6, 30))
    assert not is_active(e, date(2026, 7, 1))  # lapsed on and from expiry
    assert is_expired(e, date(2026, 7, 1))
    assert state(e, date(2026, 7, 1)) == "expired"


def test_missing_dates_mean_always_and_never():
    e = _entry()
    assert is_active(e, date(1990, 1, 1))
    assert is_active(e, date(2999, 1, 1))
    assert not is_expired(e, date(2999, 1, 1))


def test_matches_is_exact_on_site_check_and_host():
    e = _entry()
    ok = dict(site="ardctest", check_id="glance.api.image_tag")
    assert matches(e, node="oc2.example.test", **ok)
    assert not matches(e, node="oc1.example.test", **ok)
    assert not matches(e, node="oc2", **ok)  # exact certname, not a prefix
    assert not matches(e, node=None, **ok)  # site-level result: no node
    assert not matches(
        e, site="qh2", check_id="glance.api.image_tag", node="oc2.example.test"
    )
    assert not matches(
        e,
        site="ardctest",
        check_id="cinder.image_tag",
        node="oc2.example.test",
    )


def test_lint_flags_structural_errors():
    definitions = fixture_definitions()
    entries = [
        _entry(check_id="no.such_check"),
        _entry(effective="2026-07-01", expiry="2026-07-01"),
        _entry(),
        _entry(),  # duplicate grant for the same (check, site, host)
    ]
    errors, warnings = exceptions_lint(
        entries, definitions, as_of=date(2026, 6, 15)
    )
    assert any("unknown check 'no.such_check'" in e for e in errors)
    assert any("expiry 2026-07-01 is not after effective" in e for e in errors)
    assert any("granted more than once" in e for e in errors)


def test_lint_expired_is_warning_not_error():
    definitions = fixture_definitions()
    entries = [_entry(expiry="2026-01-01")]
    errors, warnings = exceptions_lint(
        entries, definitions, as_of=date(2026, 6, 15)
    )
    assert errors == []
    assert any("expired on 2026-01-01" in w for w in warnings)


def test_lint_warns_on_site_level_check():
    definitions = fixture_definitions()
    entries = [_entry(check_id="glance.api.host_count")]
    errors, warnings = exceptions_lint(
        entries, definitions, as_of=date(2026, 6, 15)
    )
    assert errors == []
    assert any("no per-node results" in w for w in warnings)


def test_fixture_exceptions_are_lint_clean():
    from conftest import CHECKS_FIXTURE

    from nectar_conformance.rules.loader import load_exceptions

    entries = load_exceptions(str(CHECKS_FIXTURE))
    errors, warnings = exceptions_lint(
        entries, fixture_definitions(), as_of=date(2026, 6, 15)
    )
    assert errors == []
    assert warnings == []
