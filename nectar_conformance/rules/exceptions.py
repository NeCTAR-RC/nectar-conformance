"""Site-scoped conformance exceptions, and their lint.

An :class:`ExceptionEntry` grants one site permission to fail one check on an explicit
list of hosts (full certnames, matched exactly), with a required reason and an optional
expiry. Entries live in ``exceptions.yaml`` in the checks repository, beside the
changelog; the file is optional and absent means no exceptions. Suppression is blanket:
any failure of the check on a listed host is excepted, whatever the observed value.

Date semantics match the changelog (date-granular, UTC): an exception is active in
``[effective, expiry)`` — on and from its ``effective`` date (absent = since always) and
strictly before its ``expiry`` date (absent = never expires). An expired entry no longer
suppresses anything; the failing result is only annotated so the lapse stays visible,
and :func:`exceptions_lint` reports it as a warning (not an error) so it gets cleaned
up or renewed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from nectar_conformance.rules.model import CheckDef


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


@dataclass(frozen=True)
class ExceptionEntry:
    """One authored exception: a site may fail one check on these hosts."""

    check_id: str
    site: str
    hosts: frozenset[str]  # full certnames, matched exactly
    reason: str
    effective: str | None = None  # ISO date; None = active since always
    expiry: str | None = None  # ISO date; None = never expires
    note: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ExceptionEntry:
        return cls(
            check_id=data["check_id"],
            site=data["site"],
            hosts=frozenset(data["hosts"]),
            reason=data["reason"],
            effective=data.get("effective"),
            expiry=data.get("expiry"),
            note=data.get("note"),
        )


def exceptions_from_dict(data: dict) -> list[ExceptionEntry]:
    return [ExceptionEntry.from_dict(e) for e in data.get("exceptions", [])]


def is_expired(entry: ExceptionEntry, as_of: date) -> bool:
    """Whether the exception has lapsed: on and from ``expiry`` it no longer applies."""
    return entry.expiry is not None and _parse_date(entry.expiry) <= as_of


def is_active(entry: ExceptionEntry, as_of: date) -> bool:
    """Whether the exception suppresses failures at ``as_of`` ([effective, expiry))."""
    if entry.effective is not None and _parse_date(entry.effective) > as_of:
        return False
    return not is_expired(entry, as_of)


def state(entry: ExceptionEntry, as_of: date) -> str:
    """One of ``active`` / ``pending`` (not yet effective) / ``expired``."""
    if is_expired(entry, as_of):
        return "expired"
    if is_active(entry, as_of):
        return "active"
    return "pending"


def matches(entry: ExceptionEntry, *, site: str, check_id: str, node) -> bool:
    """Whether the exception covers this (site, check, node); dates judged separately."""
    return (
        entry.site == site
        and entry.check_id == check_id
        and node is not None
        and node in entry.hosts
    )


def exceptions_lint(
    exceptions: list[ExceptionEntry],
    definitions: dict[str, CheckDef],
    *,
    as_of: date,
) -> tuple[list[str], list[str]]:
    """Structural problems with the exceptions file: (errors, warnings).

    Errors block (unknown check, inverted dates, colliding grants); warnings surface
    housekeeping (an expired entry, an exception on a check with no per-node results)
    without failing the lint.
    """
    errors: list[str] = []
    warnings: list[str] = []

    seen: set = set()
    for e in exceptions:
        prefix = f"{e.check_id} for site '{e.site}'"
        check = definitions.get(e.check_id)
        if check is None:
            errors.append(f"exception for unknown check '{e.check_id}'")
        if (
            e.effective is not None
            and e.expiry is not None
            and _parse_date(e.expiry) <= _parse_date(e.effective)
        ):
            errors.append(
                f"{prefix}: expiry {e.expiry} is not after effective {e.effective}"
            )
        for host in sorted(e.hosts):
            key = (e.check_id, e.site, host)
            if key in seen:
                errors.append(
                    f"{prefix}: host '{host}' is granted more than once"
                )
            seen.add(key)
        # An exception matches per-node results by certname; a count/all_equal check
        # produces a single site-level result with no node, so it can never match.
        if check is not None and (
            (check.query is not None and check.query.type == "count")
            or check.assertion_op == "all_equal"
        ):
            warnings.append(
                f"{prefix}: check has no per-node results (site-level check), "
                f"so this exception can never apply"
            )
        if is_expired(e, as_of):
            warnings.append(
                f"{prefix}: expired on {e.expiry} — remove or renew it "
                f"(hosts fail normally again)"
            )
    return errors, warnings
