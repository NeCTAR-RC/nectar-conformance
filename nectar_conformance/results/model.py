"""Result and report model.

The engine produces a :class:`Report`. The CLI and the future web dashboard both
consume it, so it is a stable, versioned contract. ``REPORT_SCHEMA_VERSION`` is bumped
when the JSON shape changes.
"""

from __future__ import annotations

from dataclasses import dataclass
import enum
from typing import Any

REPORT_SCHEMA_VERSION = "1.1"
# 1.1 adds the optional ``advisory`` block to a check result: a check may PASS today
# while a dated change is pending, carrying the upcoming value and a "due in N days"
# countdown. No new Status value; a pending change only FAILs on or after its due date.

# Severity weights used for the conformance score. Documented and versioned alongside
# REPORT_SCHEMA_VERSION so a dashboard can reproduce the number.
SEVERITY_WEIGHTS = {"error": 3, "warning": 2, "info": 1}


class Severity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Status(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"  # selector matched no nodes; check not applicable here
    UNKNOWN = (
        "unknown"  # value could not be determined; never treated as a pass
    )


# Statuses that count towards the score (i.e. the check actually applied).
APPLICABLE = (Status.PASS, Status.FAIL)


@dataclass(frozen=True)
class Provenance:
    """Where an observed value came from, for evidence and traceability."""

    source: str  # "puppetdb" | "static_repo"
    certname: str | None = None
    locator: str | None = (
        None  # e.g. "Docker::Run[glance-api].image" or fact path
    )
    collected_at: str | None = None


@dataclass(frozen=True)
class Remediation:
    """Structured "how to fix", rendered into guidance for the operator."""

    guidance: str
    hiera_key: str | None = None
    target_value: Any | None = None
    location: str | None = None  # resolved hiera file, when known


@dataclass(frozen=True)
class Advisory:
    """A dated change that is pending (announced, not yet mandatory) for this check.

    The check still PASSes while pending; the advisory tells the operator what value is
    coming, for which tier, by when, and how many days remain.
    """

    upcoming_value: Any
    due: str  # ISO date the change becomes mandatory
    days: int | None  # whole days from the report instant until ``due``
    tier: str


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check on one node (or one site-level check)."""

    rule_id: str
    title: str
    spec_section: str | None
    severity: Severity
    status: Status
    message: str
    node: str | None = None  # certname, or None for site-level checks
    observed: Any = None
    expected: Any = None
    remediation: Remediation | None = None
    provenance: Provenance | None = None
    advisory: Advisory | None = (
        None  # a pending dated change, when one applies
    )


def _rollup(statuses: list[Status]) -> Status:
    """Roll a rule's per-node statuses up to a single rule status.

    Any FAIL makes the rule FAIL. Otherwise any UNKNOWN -> UNKNOWN, any PASS -> PASS,
    and only-SKIP -> SKIP.
    """
    if not statuses:
        return Status.SKIP
    if Status.FAIL in statuses:
        return Status.FAIL
    if Status.PASS in statuses:
        return Status.PASS
    if Status.UNKNOWN in statuses:
        return Status.UNKNOWN
    return Status.SKIP


@dataclass(frozen=True)
class RuleResult:
    """All per-node results for a single rule, plus the rolled-up status."""

    rule_id: str
    title: str
    spec_section: str | None
    severity: Severity
    results: tuple[CheckResult, ...]

    @property
    def status(self) -> Status:
        return _rollup([r.status for r in self.results])

    @property
    def advisory(self) -> Advisory | None:
        """The pending dated change for this rule, if any node carries one."""
        for r in self.results:
            if r.advisory is not None:
                return r.advisory
        return None


@dataclass(frozen=True)
class Report:
    """A full conformance run for one site against one conformance version."""

    site: str
    conformance_version: str
    source: str
    generated_at: str
    rule_results: tuple[RuleResult, ...] = ()
    schema_version: str = REPORT_SCHEMA_VERSION

    @property
    def summary(self) -> dict:
        counts = {s.value: 0 for s in Status}
        for rr in self.rule_results:
            counts[rr.status.value] += 1
        return {
            "total": len(self.rule_results),
            **counts,
            "advisory": sum(
                1 for rr in self.rule_results if rr.advisory is not None
            ),
            "score": self.score,
            "result": "fail" if self.has_failures else "pass",
        }

    @property
    def has_failures(self) -> bool:
        return any(rr.status is Status.FAIL for rr in self.rule_results)

    @property
    def score(self) -> float:
        """Severity-weighted fraction of applicable checks that pass (0.0 - 1.0).

        SKIP and UNKNOWN rules are excluded from both numerator and denominator.
        """
        earned = total = 0
        for rr in self.rule_results:
            if rr.status not in APPLICABLE:
                continue
            weight = SEVERITY_WEIGHTS.get(rr.severity.value, 1)
            total += weight
            if rr.status is Status.PASS:
                earned += weight
        if total == 0:
            return 1.0
        return round(earned / total, 4)

    def worst_failing_severity(self) -> Severity | None:
        """The highest severity among failing rules, or None if nothing failed."""
        order = [Severity.ERROR, Severity.WARNING, Severity.INFO]
        failing = {
            rr.severity for rr in self.rule_results if rr.status is Status.FAIL
        }
        for sev in order:
            if sev in failing:
                return sev
        return None
