"""Dataclasses for check definitions, the conformance changelog, and resolved rules.

These are constructed only after JSON Schema validation (see loader.py), so the
``from_dict`` helpers trust their input shape.

Two layers:

* :class:`CheckDef` is the value-free LOGIC of a check (authored once).
* :class:`Changelog` is an append-only list of dated, tier-scoped :class:`ChangeEntry`
  directives that bind EXPECTED VALUES over time (and may override severity). A
  conformance "version" is a named ``tag`` (a pinned date) over the same log.

:func:`~nectar_conformance.rules.changelog.fold` combines them for one site at one
instant into a :class:`Rule` (logic + enforced value + any pending value + effective
severity) which the engine evaluates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DECLARATIVE = "declarative"
PLUGIN = "plugin"


@dataclass(frozen=True)
class Selector:
    type: str  # all | contains_class | has_resource | fact_match | site
    params: dict


@dataclass(frozen=True)
class Query:
    type: str  # fact | resource_param | count | collect
    params: dict


@dataclass(frozen=True)
class RemediationTemplate:
    guidance: str
    hiera_key: str | None = None
    hint_file: str | None = None


@dataclass(frozen=True)
class CheckDef:
    id: str
    title: str
    spec_section: str | None
    severity: str  # default severity; a manifest may override it
    kind: str  # declarative | plugin
    selector: Selector
    query: Query | None  # None for plugin checks
    assertion_op: str | None  # None for plugin checks
    remediation: RemediationTemplate | None
    plugin: dict | None  # {"name": str, "params": dict} for kind == plugin
    description: str | None = None
    # When True, a count check whose service is entirely absent (count 0) SKIPs rather
    # than FAILs: the service is optional at a site (e.g. swift). Default False, so a
    # required service (rabbitmq, mariadb, glance, ...) FAILs when it is missing.
    optional: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> CheckDef:
        sel = data["selector"]
        selector = Selector(
            type=sel["type"],
            params={k: v for k, v in sel.items() if k != "type"},
        )

        query = None
        if "query" in data:
            q = data["query"]
            query = Query(
                type=q["type"],
                params={k: v for k, v in q.items() if k != "type"},
            )

        assertion_op = None
        if "assertion" in data:
            assertion_op = data["assertion"]["op"]

        remediation = None
        if "remediation" in data:
            r = data["remediation"]
            remediation = RemediationTemplate(
                guidance=r.get("guidance", ""),
                hiera_key=r.get("hiera_key"),
                hint_file=r.get("hint_file"),
            )

        return cls(
            id=data["id"],
            title=data["title"],
            spec_section=data.get("spec_section"),
            severity=data.get("severity", "error"),
            kind=data.get("kind", DECLARATIVE),
            selector=selector,
            query=query,
            assertion_op=assertion_op,
            remediation=remediation,
            plugin=data.get("plugin"),
            description=data.get("description"),
            optional=data.get("optional", False),
        )


@dataclass(frozen=True)
class ChangeEntry:
    """One dated, tier-scoped directive in the conformance changelog.

    A directive starts mattering on its ``effective`` date and, if it carries a ``due``
    date, becomes mandatory on and from that date (before it, the directive is *pending*
    and the previously enforced value is still accepted). ``tier`` of ``all`` matches
    every site; ``test``/``prod`` scope a directive to one tier so a change can land on
    test sites earlier than production sites.
    """

    check_id: str
    effective: str  # ISO date (YYYY-MM-DD)
    value: Any = None  # bound expected value (None for present/absent checks)
    due: str | None = None  # ISO date; None means mandatory from ``effective``
    tier: str = "all"  # all | test | prod
    severity: str | None = None  # overrides the definition default when set
    note: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ChangeEntry:
        return cls(
            check_id=data["check_id"],
            effective=data["effective"],
            value=data.get("value"),
            due=data.get("due"),
            tier=data.get("tier", "all"),
            severity=data.get("severity"),
            note=data.get("note"),
        )


@dataclass(frozen=True)
class Changelog:
    """The append-only spec: a list of :class:`ChangeEntry` plus named date tags."""

    entries: tuple  # tuple[ChangeEntry, ...]
    tags: dict  # tag name -> ISO date (a pinned evaluation instant == a "version")

    @classmethod
    def from_dict(cls, data: dict) -> Changelog:
        return cls(
            entries=tuple(
                ChangeEntry.from_dict(e) for e in data.get("entries", [])
            ),
            tags=dict(data.get("tags", {})),
        )

    @property
    def check_ids(self) -> set:
        return {e.check_id for e in self.entries}


@dataclass(frozen=True)
class Rule:
    """A check definition resolved for one site at one instant.

    ``expected`` is the currently enforced value. When a change is pending (announced but
    not yet due), ``pending_value``/``pending_due`` describe the upcoming target and the
    engine accepts either value, emitting an advisory countdown.
    """

    check: CheckDef
    expected: Any  # enforced value (None for present/absent/plugin)
    severity: str  # effective severity (changelog override or the definition default)
    tier: str = "all"  # the site tier this rule was folded for
    due: str | None = None  # the enforced entry's due date, if any
    pending_value: Any = (
        None  # upcoming target value while a change is pending
    )
    pending_due: str | None = (
        None  # ISO date the pending change becomes mandatory
    )
    pending_days: int | None = (
        None  # whole days from the fold instant until pending_due
    )
    has_pending: bool = (
        False  # explicit, since pending_value may legitimately be None
    )

    # Convenience passthroughs so the engine and reporters do not reach into .check.
    @property
    def id(self) -> str:
        return self.check.id

    @property
    def title(self) -> str:
        return self.check.title

    @property
    def spec_section(self) -> str | None:
        return self.check.spec_section

    @property
    def kind(self) -> str:
        return self.check.kind

    @property
    def selector(self) -> Selector:
        return self.check.selector

    @property
    def query(self) -> Query | None:
        return self.check.query

    @property
    def assertion_op(self) -> str | None:
        return self.check.assertion_op

    @property
    def remediation(self) -> RemediationTemplate | None:
        return self.check.remediation

    @property
    def optional(self) -> bool:
        return self.check.optional
