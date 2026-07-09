"""Serialise folded Rules and per-site summaries for the JSON API.

Reports already serialise via :mod:`nectar_conformance.results.serialise`; this covers the
folded :class:`~nectar_conformance.rules.model.Rule` (the "requirements"/"pending" views)
and the compact per-site summary shown on the sites list.
"""

from __future__ import annotations

_SEVERITY_ORDER = ("error", "warning", "info")


def _remediation_to_dict(rem) -> dict | None:
    if rem is None:
        return None
    return {
        "guidance": rem.guidance,
        "hiera_key": rem.hiera_key,
        "hint_file": rem.hint_file,
    }


def rule_to_dict(rule) -> dict:
    """A folded Rule as the API exposes it (logic id/title + enforced and pending values)."""
    return {
        "id": rule.id,
        "title": rule.title,
        "spec_section": rule.spec_section,
        "severity": rule.severity,
        "expected": rule.expected,
        "optional": rule.optional,
        "due": rule.due,
        "has_pending": rule.has_pending,
        "pending_value": rule.pending_value,
        "pending_due": rule.pending_due,
        "pending_days": rule.pending_days,
        "remediation": _remediation_to_dict(rule.remediation),
    }


def worst_failing_severity(report: dict) -> str | None:
    """Highest severity among a report's failing rules, or None if nothing failed."""
    failing = {
        rr.get("severity")
        for rr in report.get("results", [])
        if rr.get("status") == "fail"
    }
    for severity in _SEVERITY_ORDER:
        if severity in failing:
            return severity
    return None


def site_summary(site: str, report: dict, error: str | None = None) -> dict:
    """Compact per-site entry for the sites list.

    ``error`` is the site's failure from the most recent refresh, if any; a summary can
    carry both a (last good, now stale) report and an error.
    """
    return {
        "site": site,
        "summary": report.get("summary"),
        "generated_at": report.get("generated_at"),
        "conformance_version": report.get("conformance_version"),
        "worst_severity": worst_failing_severity(report),
        "error": error,
    }
