"""The pure rollout/adoption join buckets sites correctly per change."""

from __future__ import annotations

from datetime import date
from typing import Any

from nectar_conformance.rollout import (
    ADOPTED,
    NOT_APPLICABLE,
    OVERDUE,
    PENDING,
    rollout_status,
)

AS_OF = date(2026, 6, 17)
FUTURE = "2026-12-31"
PAST = "2026-01-01"


def _report(results):
    return {"results": results}


def _rule(check_id, status, checks):
    return {"rule_id": check_id, "status": status, "checks": checks}


def _check(observed: Any, status: str = "pass", node: str | None = "n1"):
    return {"observed": observed, "status": status, "node": node}


def _change(
    due: str, op: str = "equals", target: Any = "v2", check_id: str = "img"
):
    return {"check_id": check_id, "op": op, "target": target, "due": due}


def test_adopted_vs_pending_before_due():
    reports = {
        "a": _report([_rule("img", "pass", [_check("v2")])]),
        "b": _report([_rule("img", "pass", [_check("v1")])]),
    }
    result = rollout_status([_change(FUTURE)], reports, AS_OF)[0]
    assert result["buckets"][ADOPTED] == ["a"]
    assert result["buckets"][PENDING] == ["b"]
    assert result["due_passed"] is False
    assert result["counts"] == {
        ADOPTED: 1,
        PENDING: 1,
        OVERDUE: 0,
        NOT_APPLICABLE: 0,
    }


def test_overdue_after_due():
    reports = {
        "a": _report([_rule("img", "pass", [_check("v2")])]),
        "b": _report([_rule("img", "fail", [_check("v1", "fail")])]),
    }
    result = rollout_status([_change(PAST)], reports, AS_OF)[0]
    assert result["buckets"][ADOPTED] == ["a"]
    assert result["buckets"][OVERDUE] == ["b"]
    assert result["due_passed"] is True


def test_not_applicable_when_skipped_unknown_or_missing():
    reports = {
        "c": _report([_rule("img", "skip", [])]),
        "d": _report([]),
        "e": _report([_rule("img", "unknown", [_check(None, "unknown")])]),
    }
    result = rollout_status([_change(FUTURE)], reports, AS_OF)[0]
    assert sorted(result["buckets"][NOT_APPLICABLE]) == ["c", "d", "e"]


def test_per_node_requires_all_nodes_to_adopt():
    reports = {
        "f": _report(
            [
                _rule(
                    "img",
                    "pass",
                    [_check("v2", node="n1"), _check("v2", node="n2")],
                )
            ]
        ),
        "g": _report(
            [
                _rule(
                    "img",
                    "fail",
                    [_check("v2", node="n1"), _check("v1", "fail", "n2")],
                )
            ]
        ),
    }
    result = rollout_status([_change(FUTURE)], reports, AS_OF)[0]
    assert result["buckets"][ADOPTED] == ["f"]
    assert result["buckets"][PENDING] == ["g"]


def test_count_gte_site_level_op():
    reports = {
        "h": _report([_rule("hc", "pass", [_check(3, node=None)])]),
        "i": _report([_rule("hc", "fail", [_check(2, "fail", None)])]),
    }
    change = _change(PAST, op="count_gte", target=3, check_id="hc")
    result = rollout_status([change], reports, AS_OF)[0]
    assert result["buckets"][ADOPTED] == ["h"]
    assert result["buckets"][OVERDUE] == ["i"]


def test_in_set_op():
    reports = {
        "j": _report([_rule("os", "pass", [_check("24.04")])]),
        "k": _report([_rule("os", "fail", [_check("20.04", "fail")])]),
    }
    change = _change(
        PAST, op="in_set", target=["24.04", "22.04"], check_id="os"
    )
    result = rollout_status([change], reports, AS_OF)[0]
    assert result["buckets"][ADOPTED] == ["j"]
    assert result["buckets"][OVERDUE] == ["k"]


def test_unevaluable_operator_is_not_applicable():
    # count_gte on a non-numeric observation raises; rollout treats it as N/A, not a crash.
    reports = {
        "l": _report([_rule("hc", "fail", [_check("abc", "fail", None)])])
    }
    change = _change(PAST, op="count_gte", target=3, check_id="hc")
    result = rollout_status([change], reports, AS_OF)[0]
    assert result["buckets"][NOT_APPLICABLE] == ["l"]
