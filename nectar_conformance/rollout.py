"""Pure rollout/adoption join: which sites have done each dated change.

A "change" is a dated changelog directive (a new expected value with a ``due`` date). Given
the latest stored Report per site, bucket each site for each change into adopted / pending /
overdue / not_applicable, reusing the engine's operator vocabulary so ``equals``, ``in_set``,
``count_gte`` ... are judged exactly as the engine would. Pure: no I/O, no config; it takes
plain dicts (the report JSON the web store reads) so it is trivially testable and decoupled
from how the reports were produced.
"""

from __future__ import annotations

from datetime import date

from nectar_conformance.engine.operators import apply as _apply_op

ADOPTED = "adopted"
PENDING = "pending"
OVERDUE = "overdue"
NOT_APPLICABLE = "not_applicable"

# Statuses where the check actually applied to the site (so adoption is meaningful).
_APPLICABLE_STATUSES = ("pass", "fail")


def _rule_result(report: dict, check_id: str) -> dict | None:
    for rr in report.get("results", []):
        if rr.get("rule_id") == check_id:
            return rr
    return None


def _site_meets(rule_result: dict, op: str, target) -> bool | None:
    """Whether a site already satisfies ``target`` for this check, or None if N/A.

    N/A when the check did not apply (skipped/unknown, or the operator could not be
    evaluated). Otherwise every applicable per-node (or single site-level) observation must
    satisfy the operator against the target. Comparing observed-vs-target directly, rather
    than trusting the report's pass/fail, is correct in both regimes: while a change is
    pending the engine accepts the old value too, so its pass/fail cannot tell adopters apart.
    """
    if rule_result.get("status") in ("skip", "unknown"):
        return None
    applicable = [
        c
        for c in rule_result.get("checks", [])
        if c.get("status") in _APPLICABLE_STATUSES
    ]
    if not applicable:
        return None
    try:
        return all(
            _apply_op(op, c.get("observed"), target) for c in applicable
        )
    except Exception:
        # An operator that cannot judge these values (bad version string, etc.) is treated
        # as not-determinable rather than crashing the dashboard.
        return None


def _bucket(meets: bool | None, due: date | None, as_of: date) -> str:
    if meets is None:
        return NOT_APPLICABLE
    if meets:
        return ADOPTED
    if due is not None and due > as_of:
        return PENDING  # not done yet, but the deadline has not passed
    return OVERDUE  # not done and the deadline has passed


def rollout_status(
    changes: list[dict], reports_by_site: dict[str, dict], as_of: date
) -> list[dict]:
    """Bucket every site against every change.

    ``changes`` come from :func:`nectar_conformance.service.list_changes` (each has
    ``check_id``, ``op``, ``target``, ``due``). ``reports_by_site`` maps site id -> stored
    report dict. Returns one entry per change with a ``buckets`` mapping (bucket -> sorted
    site ids), a ``counts`` summary, and ``due_passed``.
    """
    out: list[dict] = []
    for change in changes:
        due = date.fromisoformat(change["due"]) if change.get("due") else None
        buckets: dict[str, list[str]] = {
            ADOPTED: [],
            PENDING: [],
            OVERDUE: [],
            NOT_APPLICABLE: [],
        }
        for site in sorted(reports_by_site):
            rule_result = _rule_result(
                reports_by_site[site], change["check_id"]
            )
            if rule_result is None:
                buckets[NOT_APPLICABLE].append(site)
                continue
            meets = _site_meets(rule_result, change["op"], change["target"])
            buckets[_bucket(meets, due, as_of)].append(site)
        out.append(
            {
                **change,
                "due_passed": bool(due is not None and due <= as_of),
                "buckets": buckets,
                "counts": {
                    name: len(sites) for name, sites in buckets.items()
                },
            }
        )
    return out
