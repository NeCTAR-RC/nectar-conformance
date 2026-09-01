"""Apply site-scoped exceptions to a finished report.

The engine stays exception-unaware (``evaluate`` is a pure function of model + rules);
this is the one module that sees both the result layer and the authored
:class:`~nectar_conformance.rules.exceptions.ExceptionEntry` data. It is a pure
``Report -> Report`` transform: an active matching exception downgrades a FAIL to
EXCEPTED (before rollup, so the rule no longer counts as failing), an expired matching
exception leaves the FAIL standing and only annotates it. ``RuleResult.status`` and
``Report.summary`` are computed properties, so replacing the per-node statuses is all
that is needed.
"""

from __future__ import annotations

import dataclasses
from datetime import date

from nectar_conformance.results.model import (
    CheckResult,
    ExceptionNote,
    Report,
    Status,
)
from nectar_conformance.rules.exceptions import (
    ExceptionEntry,
    is_active,
    is_expired,
    matches,
)


def _note(entry: ExceptionEntry, *, expired: bool) -> ExceptionNote:
    return ExceptionNote(
        reason=entry.reason,
        expiry=entry.expiry,
        expired=expired,
        note=entry.note,
    )


def _transform(
    check: CheckResult,
    site: str,
    entries: list[ExceptionEntry],
    as_of: date,
) -> CheckResult:
    if check.status is not Status.FAIL or check.node is None:
        return check
    matching = [
        e
        for e in entries
        if matches(e, site=site, check_id=check.rule_id, node=check.node)
    ]
    for entry in matching:
        if is_active(entry, as_of):
            return dataclasses.replace(
                check,
                status=Status.EXCEPTED,
                exception=_note(entry, expired=False),
            )
    for entry in matching:
        if is_expired(entry, as_of):
            return dataclasses.replace(
                check, exception=_note(entry, expired=True)
            )
    return check  # matched only not-yet-effective entries (or none): untouched


def apply_exceptions(
    report: Report,
    exceptions: list[ExceptionEntry],
    *,
    as_of: date,
) -> Report:
    """Return ``report`` with the site's exceptions applied at ``as_of``."""
    entries = [e for e in exceptions if e.site == report.site]
    if not entries:
        return report
    rule_results = tuple(
        dataclasses.replace(
            rr,
            results=tuple(
                _transform(c, report.site, entries, as_of) for c in rr.results
            ),
        )
        for rr in report.rule_results
    )
    return dataclasses.replace(report, rule_results=rule_results)
