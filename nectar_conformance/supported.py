"""Pure "what may a node run?" view over a folded rule set.

An operator asks "which Ubuntu releases may the controllers run?" or "which MariaDB
series may the database nodes run?". At one instant the answer is everything the
engine accepts: the fold's **enforced** value plus, while a change is pending, the
**pending** value the engine already accepts early. This module flattens each
rule's expected value(s) into individual *options* and tags each with how long it
stays accepted. Every option is accepted now; the tag says what happens next:

* ``current`` -- nothing scheduled: still accepted after any pending change;
* ``ending``  -- dropped by the pending change: unsupported on and from ``due``;
* ``new``     -- added by the pending change (so it only appeared when the change
                 was announced) and still accepted once it falls due on ``due``.

A list value (``in_set``) fans out to one option per member; a scalar or pattern
value is a single option. Rules without a bound value (present/absent/plugin
checks) have nothing to list and are omitted. Pure: no I/O, no config; it takes
folded :class:`~nectar_conformance.rules.model.Rule` objects and returns plain
dicts for the API.
"""

from __future__ import annotations

from typing import Any

from nectar_conformance.rules.model import Rule

CURRENT = "current"
ENDING = "ending"
NEW = "new"


def _as_options(value: Any) -> list:
    """One entry per accepted value: a list fans out, anything else is one option."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _option(value: Any, status: str, due: str | None) -> dict:
    return {"value": value, "status": status, "due": due}


def rule_options(rule: Rule) -> list[dict]:
    """The accepted values of one rule, each tagged current / ending / new.

    Enforced values keep their changelog order, followed by any pending values
    not already enforced. Membership is by equality, so a pattern mapping that
    appears in both the enforced and the pending value counts as the same option.
    """
    enforced = _as_options(rule.expected)
    if not rule.has_pending:
        return [_option(v, CURRENT, None) for v in enforced]
    pending = _as_options(rule.pending_value)
    due = rule.pending_due
    options = []
    for v in enforced:
        if v in pending:
            options.append(_option(v, CURRENT, None))
        else:
            options.append(_option(v, ENDING, due))
    options.extend(_option(v, NEW, due) for v in pending if v not in enforced)
    return options


def supported_options(rules: list[Rule]) -> list[dict]:
    """Every value-bearing rule with its tagged options, in rule order.

    Each entry carries the check's identity and ``spec_section`` (the node type
    the check belongs to, which a consumer groups by), the assertion ``op`` (so a
    value can be phrased as "at least N" or "N or newer"), and the pending due
    date when a change is in flight. Rules with no options are dropped.
    """
    out: list[dict] = []
    for rule in rules:
        options = rule_options(rule)
        if not options:
            continue
        out.append(
            {
                "id": rule.id,
                "title": rule.title,
                "spec_section": rule.spec_section,
                "op": rule.assertion_op,
                "optional": rule.optional,
                "pending_due": rule.pending_due if rule.has_pending else None,
                "options": options,
            }
        )
    return out
