"""The pure rollout/adoption join buckets sites correctly per change."""

from __future__ import annotations

from datetime import date
from typing import Any

from nectar_conformance.rollout import (
    ADOPTED,
    DUE_SOON,
    NOT_APPLICABLE,
    OVERDUE,
    PENDING,
    actionable,
    rollout_status,
    site_rollout,
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


# --- site_rollout: the per-site pivot -------------------------------------------------

SOON = "2026-06-27"  # AS_OF + 10 days
LATER = "2026-08-16"  # AS_OF + 60 days


def test_site_rollout_pivots_buckets_per_site():
    reports = {
        # "a" adopted the img change but is overdue on the os change.
        "a": _report(
            [
                _rule("img", "pass", [_check("v2")]),
                _rule("os", "fail", [_check("20.04", "fail")]),
            ]
        ),
        # "b" is pending on img and adopted on os.
        "b": _report(
            [
                _rule("img", "pass", [_check("v1")]),
                _rule("os", "pass", [_check("24.04")]),
            ]
        ),
    }
    changes = [
        _change(SOON, check_id="img"),
        _change(PAST, op="in_set", target=["24.04"], check_id="os"),
    ]
    pivot = site_rollout(rollout_status(changes, reports, AS_OF), AS_OF)

    a, b = pivot["a"], pivot["b"]
    assert [r["check_id"] for r in a[OVERDUE]] == ["os"]
    assert a[OVERDUE][0]["days"] == (date(2026, 1, 1) - AS_OF).days < 0
    assert a[PENDING] == []
    assert [r["check_id"] for r in a[ADOPTED]] == ["img"]
    assert a["counts"] == {OVERDUE: 1, PENDING: 0, DUE_SOON: 0, ADOPTED: 1}
    assert a["next_due"] is None

    assert [r["check_id"] for r in b[PENDING]] == ["img"]
    assert b[PENDING][0]["days"] == 10
    assert [r["check_id"] for r in b[ADOPTED]] == ["os"]
    assert b["counts"] == {OVERDUE: 0, PENDING: 1, DUE_SOON: 1, ADOPTED: 1}
    assert b["next_due"] == SOON


def test_site_rollout_due_soon_window():
    reports = {"a": _report([_rule("img", "pass", [_check("v1")])])}
    changes = [_change(SOON), _change(LATER, check_id="img2")]
    reports["a"]["results"].append(_rule("img2", "pass", [_check("v1")]))
    rollout = rollout_status(changes, reports, AS_OF)

    wide = site_rollout(rollout, AS_OF, due_soon_days=30)["a"]
    assert wide["counts"] == {
        OVERDUE: 0,
        PENDING: 2,
        DUE_SOON: 1,
        ADOPTED: 0,
    }
    assert wide["next_due"] == SOON

    narrow = site_rollout(rollout, AS_OF, due_soon_days=5)["a"]
    assert narrow["counts"][DUE_SOON] == 0
    assert narrow["counts"][PENDING] == 2


def test_site_rollout_adopted_and_na_sites():
    # An adopted site carries the change ref (so a UI can show its status); a site the
    # change never applied to gets the explicit zero entry, distinct from "no data".
    reports = {
        "adopted": _report([_rule("img", "pass", [_check("v2")])]),
        "na": _report([_rule("img", "skip", [])]),
    }
    pivot = site_rollout(
        rollout_status([_change(FUTURE)], reports, AS_OF), AS_OF
    )
    done = pivot["adopted"]
    assert [r["check_id"] for r in done[ADOPTED]] == ["img"]
    assert done["counts"] == {OVERDUE: 0, PENDING: 0, DUE_SOON: 0, ADOPTED: 1}
    assert done["next_due"] is None

    quiet = pivot["na"]
    assert quiet[OVERDUE] == quiet[PENDING] == quiet[ADOPTED] == []
    assert quiet["counts"] == {OVERDUE: 0, PENDING: 0, DUE_SOON: 0, ADOPTED: 0}
    assert quiet["next_due"] is None


def test_site_rollout_empty_changes_is_empty():
    assert site_rollout([], AS_OF) == {}


def test_site_rollout_missing_due_is_never_due_soon():
    # Defensive: list_changes always sets due, but the pivot must not crash without it.
    reports = {"a": _report([_rule("img", "fail", [_check("v1", "fail")])])}
    rollout = rollout_status(
        [{"check_id": "img", "op": "equals", "target": "v2", "due": None}],
        reports,
        AS_OF,
    )
    view = site_rollout(rollout, AS_OF)["a"]
    assert [r["check_id"] for r in view[OVERDUE]] == ["img"]
    assert view[OVERDUE][0]["days"] is None
    assert view["counts"] == {OVERDUE: 1, PENDING: 0, DUE_SOON: 0, ADOPTED: 0}


def test_actionable_drops_finished_changes():
    reports = {
        "a": _report(
            [
                _rule("img", "pass", [_check("v2")]),
                _rule("os", "pass", [_check("24.04")]),
                _rule("hc", "fail", [_check(2, "fail", None)]),
            ]
        ),
    }
    changes = [
        # Done: due passed and everyone has adopted; nothing left to act on.
        _change(PAST, check_id="img"),
        # Still in flight: not yet due (even though "a" already adopted it).
        _change(FUTURE, op="in_set", target=["24.04"], check_id="os"),
        # Still in flight: due passed but "a" is behind.
        _change(PAST, op="count_gte", target=3, check_id="hc"),
    ]
    live = actionable(rollout_status(changes, reports, AS_OF))
    assert [c["check_id"] for c in live] == ["os", "hc"]
    # The pivot over actionable changes never sees the finished rollout.
    view = site_rollout(live, AS_OF)["a"]
    assert [r["check_id"] for r in view[ADOPTED]] == ["os"]
    assert [r["check_id"] for r in view[OVERDUE]] == ["hc"]
