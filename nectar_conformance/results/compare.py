"""Compare two conformance reports (the JSON produced by ``check run --format json``).

Used to answer "will this change fix conformance, and does it break anything?" by
diffing a baseline report against the report for a proposed change.
"""

from __future__ import annotations


def _index(report: dict) -> dict:
    return {r["rule_id"]: r for r in report.get("results", [])}


def compare_reports(old: dict, new: dict) -> dict:
    """Classify how each check's status changed from ``old`` to ``new``.

    Returns lists of {rule_id, severity, old, new}: ``fixed`` (was failing, now passes),
    ``regressed`` (was passing, now fails), ``still_failing``, plus ``added`` / ``removed``
    checks (e.g. when the conformance version differs between runs).
    """
    o, n = _index(old), _index(new)
    fixed, regressed, still_failing, added, removed = [], [], [], [], []

    for rule_id in sorted(set(o) | set(n)):
        old_r, new_r = o.get(rule_id), n.get(rule_id)
        if old_r is None:
            added.append(
                {
                    "rule_id": rule_id,
                    "severity": new_r["severity"],
                    "old": None,
                    "new": new_r["status"],
                }
            )
            continue
        if new_r is None:
            removed.append(
                {
                    "rule_id": rule_id,
                    "severity": old_r["severity"],
                    "old": old_r["status"],
                    "new": None,
                }
            )
            continue
        os_, ns = old_r["status"], new_r["status"]
        row = {
            "rule_id": rule_id,
            "severity": new_r["severity"],
            "old": os_,
            "new": ns,
        }
        if os_ == "fail" and ns == "pass":
            fixed.append(row)
        elif os_ != "fail" and ns == "fail":
            regressed.append(row)
        elif os_ == "fail" and ns == "fail":
            still_failing.append(row)

    return {
        "fixed": fixed,
        "regressed": regressed,
        "still_failing": still_failing,
        "added": added,
        "removed": removed,
    }
