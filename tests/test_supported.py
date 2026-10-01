"""The pure supported-options view tags each accepted value correctly."""

from __future__ import annotations

from typing import Any

from nectar_conformance.rules.model import CheckDef, Rule, Selector
from nectar_conformance.supported import (
    CURRENT,
    ENDING,
    NEW,
    rule_options,
    supported_options,
)

DUE = "2027-02-01"


def _rule(
    expected: Any,
    *,
    pending: Any = None,
    has_pending: bool = False,
    op: str | None = "in_set",
    optional: bool = False,
) -> Rule:
    check = CheckDef(
        id="os.controller.ubuntu",
        title="Controllers run an approved Ubuntu release",
        spec_section="OpenStack Controller",
        kind="declarative",
        selector=Selector(type="all", params={}),
        query=None,
        assertion_op=op,
        remediation=None,
        plugin=None,
        optional=optional,
    )
    return Rule(
        check=check,
        expected=expected,
        has_pending=has_pending,
        pending_value=pending,
        pending_due=DUE if has_pending else None,
        pending_days=120 if has_pending else None,
    )


def _tagged(options):
    return [(o["value"], o["status"], o["due"]) for o in options]


def test_list_without_pending_is_all_current():
    options = rule_options(_rule(["24.04", "22.04"]))
    assert _tagged(options) == [
        ("24.04", CURRENT, None),
        ("22.04", CURRENT, None),
    ]


def test_scalar_is_a_single_option():
    assert _tagged(rule_options(_rule("3.13.7-1", op="equals"))) == [
        ("3.13.7-1", CURRENT, None)
    ]


def test_value_free_rule_has_no_options_and_is_dropped():
    rule = _rule(None, op="present")
    assert rule_options(rule) == []
    assert supported_options([rule]) == []


def test_narrowing_marks_dropped_values_ending():
    # 22.04 is still accepted today but not once the pending set applies.
    options = rule_options(
        _rule(["24.04", "22.04"], pending=["24.04"], has_pending=True)
    )
    assert _tagged(options) == [
        ("24.04", CURRENT, None),
        ("22.04", ENDING, DUE),
    ]


def test_widening_marks_added_values_new_after_the_enforced_ones():
    options = rule_options(
        _rule(
            ["24.04", "22.04"],
            pending=["24.04", "26.04"],
            has_pending=True,
        )
    )
    assert _tagged(options) == [
        ("24.04", CURRENT, None),
        ("22.04", ENDING, DUE),
        ("26.04", NEW, DUE),
    ]


def test_scalar_swap_is_one_ending_and_one_new():
    options = rule_options(
        _rule("3.13.7-1", pending="4.2.*", has_pending=True, op="equals")
    )
    assert _tagged(options) == [
        ("3.13.7-1", ENDING, DUE),
        ("4.2.*", NEW, DUE),
    ]


def test_pattern_values_compare_by_equality():
    same = {"regex": r"24\..*"}
    assert _tagged(
        rule_options(_rule(same, pending=dict(same), has_pending=True))
    ) == [(same, CURRENT, None)]

    newer = {"regex": r"26\.3\..*"}
    assert _tagged(
        rule_options(_rule(same, pending=newer, has_pending=True))
    ) == [(same, ENDING, DUE), (newer, NEW, DUE)]


def test_supported_options_carries_check_context():
    plain = _rule(["10.11"], op="in_set")
    changing = _rule(
        2, pending=3, has_pending=True, op="count_gte", optional=True
    )
    out = supported_options([plain, changing])
    assert [c["id"] for c in out] == [plain.id, changing.id]

    first, second = out
    assert first["title"] == plain.title
    assert first["spec_section"] == "OpenStack Controller"
    assert first["op"] == "in_set"
    assert first["optional"] is False
    assert first["pending_due"] is None
    assert _tagged(first["options"]) == [("10.11", CURRENT, None)]

    assert second["op"] == "count_gte"
    assert second["optional"] is True
    assert second["pending_due"] == DUE
    assert _tagged(second["options"]) == [(2, ENDING, DUE), (3, NEW, DUE)]
