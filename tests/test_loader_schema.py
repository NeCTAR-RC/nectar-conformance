"""The loader reads a checks dir and validates it; malformed data is rejected.

The check data lives in the nectar-conformance-checks repo; here we load the suite's
own mirror (tests/fixtures/checks) so these stay independent of any external checkout.
"""

from conftest import CHECKS_FIXTURE
import pytest

from nectar_conformance.errors import RuleError
from nectar_conformance.rules.loader import load_changelog, load_definitions
from nectar_conformance.rules.schema import (
    validate_changelog,
    validate_definition,
)


def test_definitions_and_changelog_load_from_a_dir():
    definitions = load_definitions(str(CHECKS_FIXTURE))
    changelog = load_changelog(str(CHECKS_FIXTURE))
    assert "glance.api.image_tag" in definitions
    assert "2026.1" in changelog.tags


def test_loader_requires_a_checks_dir():
    # No packaged fallback: an unconfigured dir is an actionable error, not empty data.
    with pytest.raises(RuleError):
        load_definitions()
    with pytest.raises(RuleError):
        load_changelog()


def test_every_changelog_entry_has_a_definition():
    definitions = load_definitions(str(CHECKS_FIXTURE))
    changelog = load_changelog(str(CHECKS_FIXTURE))
    for check_id in changelog.check_ids:
        assert check_id in definitions, (
            f"changelog references unknown {check_id}"
        )


def test_malformed_definition_rejected():
    bad = {"id": "bad", "title": "no selector"}  # missing required selector
    with pytest.raises(RuleError):
        validate_definition(bad)


def test_unknown_operator_in_definition_rejected():
    bad = {
        "id": "bad.op",
        "title": "bad operator",
        "selector": {"type": "all"},
        "query": {"type": "fact", "path": "x"},
        "assertion": {"op": "not_a_real_op"},
    }
    with pytest.raises(RuleError):
        validate_definition(bad)


def _composite(selector):
    return {
        "id": "x.composite",
        "title": "composite selector",
        "selector": selector,
        "query": {"type": "fact", "path": "kmods.kvm_intel.parameters.nested"},
        "assertion": {"op": "in_set"},
    }


def test_composite_selector_accepted():
    validate_definition(
        _composite(
            {
                "type": "all_of",
                "selectors": [
                    {"type": "contains_class", "class": "c"},
                    {"type": "fact_match", "path": "p", "match": "present"},
                ],
            }
        )
    )


def test_nested_composite_selector_rejected():
    # all_of is one level deep: a composite may not contain another composite.
    inner = {
        "type": "all_of",
        "selectors": [{"type": "all"}, {"type": "all"}],
    }
    with pytest.raises(RuleError):
        validate_definition(
            _composite(
                {"type": "all_of", "selectors": [inner, {"type": "all"}]}
            )
        )


def test_composite_selector_needs_two_clauses():
    with pytest.raises(RuleError):
        validate_definition(
            _composite({"type": "all_of", "selectors": [{"type": "all"}]})
        )


def test_unknown_fact_match_mode_rejected():
    with pytest.raises(RuleError):
        validate_definition(
            _composite(
                {"type": "fact_match", "path": "p", "match": "sometimes"}
            )
        )


def test_malformed_changelog_rejected():
    bad = {
        "entries": [{"check_id": "a.b"}]
    }  # entry missing required 'effective'
    with pytest.raises(RuleError):
        validate_changelog(bad)


def test_changelog_bad_date_rejected():
    bad = {"entries": [{"check_id": "a.b", "effective": "1 June 2026"}]}
    with pytest.raises(RuleError):
        validate_changelog(bad)
