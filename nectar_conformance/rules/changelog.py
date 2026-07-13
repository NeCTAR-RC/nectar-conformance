"""Fold the conformance changelog into a concrete rule set, and lint it.

The spec is an append-only :class:`~nectar_conformance.rules.model.Changelog` of dated,
tier-scoped :class:`~nectar_conformance.rules.model.ChangeEntry` directives. There is no
``<major>.<minor>`` tree: a conformance "version" is a named ``tag`` (a pinned date) over
the same log.

The expected state for one site at one instant is the *fold* of the changelog:

* keep the entries whose ``tier`` matches the site (``all`` always matches) and whose
  ``effective`` date is on or before the instant;
* the **enforced value** is the latest-effective such entry that is already mandatory
  (``due`` is absent, or ``due`` is on or before the instant);
* a **pending target** is the nearest entry that is announced but not yet mandatory
  (``effective <= instant < due``), surfaced so the engine can accept it early and emit a
  "due in N days" advisory.

Date semantics: dates are date-granular, UTC. A change is enforced **on and from** its due
date (``instant >= due``), and pending **strictly before** it.
"""

from __future__ import annotations

from datetime import date
import re

from nectar_conformance.errors import RuleError, VersionError
from nectar_conformance.rules.model import (
    ChangeEntry,
    Changelog,
    CheckDef,
    Rule,
)

# Conformance version (tag) names: YYYY.N, matching schema.json's tag propertyNames.
_TAG_NAME_RE = re.compile(r"^[0-9]+\.[0-9]+$")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _tier_matches(entry_tier: str, site_tier: str) -> bool:
    return entry_tier == "all" or entry_tier == site_tier


def resolve_tag(changelog: Changelog, name: str) -> date:
    """Resolve a named tag to its pinned evaluation date."""
    pinned = changelog.tags.get(name)
    if pinned is None:
        raise VersionError(f"unknown conformance version '{name}'")
    return _parse_date(pinned)


def _visible(
    changelog: Changelog, check_id: str, tier: str, as_of: date
) -> list[ChangeEntry]:
    """Entries for a check that the site can see at ``as_of`` (tier + effective filtered)."""
    out = [
        e
        for e in changelog.entries
        if e.check_id == check_id
        and _tier_matches(e.tier, tier)
        and _parse_date(e.effective) <= as_of
    ]
    # Stable order: by effective date, then by original position (already sorted-ish).
    return sorted(out, key=lambda e: _parse_date(e.effective))


def _fold_check(visible: list[ChangeEntry], as_of: date) -> dict | None:
    """Resolve the visible entries of one check to enforced + pending state.

    Returns None when no value is enforced yet (the check is announced but not mandatory,
    so it does not apply at this instant) and there is therefore nothing to evaluate.
    """
    enforced: list[ChangeEntry] = []
    pending: list[tuple[ChangeEntry, date]] = []  # (entry, parsed due)
    for e in visible:
        if e.due is None:
            enforced.append(e)
            continue
        due = _parse_date(e.due)
        if due <= as_of:
            enforced.append(e)
        else:
            pending.append((e, due))
    if not enforced:
        return None  # not yet mandatory for this site at this instant

    # Latest-effective enforced entry wins; ties resolved by list order (last wins).
    enforced_entry = enforced[-1]
    state = {
        "value": enforced_entry.value,
        "effective": enforced_entry.effective,  # winner's date; squash baselines keep it
        "due": enforced_entry.due,
        "pending_value": None,
        "pending_due": None,
        "pending_days": None,
        "has_pending": False,
    }
    if pending:
        # The nearest upcoming deadline is the next target the site must reach.
        nearest_entry, nearest_due = min(pending, key=lambda pair: pair[1])
        state.update(
            pending_value=nearest_entry.value,
            pending_due=nearest_entry.due,
            pending_days=(nearest_due - as_of).days,
            has_pending=True,
        )
    return state


def fold(
    changelog: Changelog,
    definitions: dict[str, CheckDef],
    *,
    tier: str,
    as_of: date,
) -> list[Rule]:
    """Produce the rule set enforced for ``tier`` at ``as_of`` (logic + values)."""
    rules: list[Rule] = []
    for check_id in sorted(changelog.check_ids):
        visible = _visible(changelog, check_id, tier, as_of)
        state = _fold_check(visible, as_of)
        if state is None:
            continue
        check = definitions.get(check_id)
        if check is None:
            raise RuleError(f"changelog references unknown check '{check_id}'")
        rules.append(
            Rule(
                check=check,
                expected=state["value"],
                tier=tier,
                due=state["due"],
                pending_value=state["pending_value"],
                pending_due=state["pending_due"],
                pending_days=state["pending_days"],
                has_pending=state["has_pending"],
            )
        )
    return rules


def resolved_check_ids_at(changelog: Changelog, tier: str, as_of: date) -> set:
    """The set of check ids that are enforced for ``tier`` at ``as_of``."""
    out = set()
    for check_id in changelog.check_ids:
        visible = _visible(changelog, check_id, tier, as_of)
        if _fold_check(visible, as_of) is not None:
            out.add(check_id)
    return out


def _baseline_entries(
    check_id: str,
    note: str,
    test_state: dict | None,
    prod_state: dict | None,
) -> list[ChangeEntry]:
    """Baseline directive(s) reproducing one check's enforced state, ``due`` stripped.

    Each baseline keeps the *winning* enforced entry's ``effective`` date (not the squash
    date), so that a carried-forward pending entry with an earlier ``effective`` still wins
    once its ``due`` passes; using the squash date here would let the baseline outrank it and
    silently drop the rollout. Tiers collapse to a single ``tier: all`` entry only when test
    and prod enforce the same value and effective date; otherwise per-tier entries are
    emitted. Emits one entry when only one tier is enforced; nothing when neither is (the
    check survives only via carried-forward entries).
    """

    def entry(tier: str, state: dict) -> ChangeEntry:
        return ChangeEntry(
            check_id=check_id,
            effective=state["effective"],
            value=state["value"],
            due=None,
            tier=tier,
            note=note,
        )

    if test_state is not None and prod_state is not None:
        same = (test_state["value"], test_state["effective"]) == (
            prod_state["value"],
            prod_state["effective"],
        )
        if same:
            return [entry("all", prod_state)]
        return [entry("test", test_state), entry("prod", prod_state)]
    if test_state is not None:
        return [entry("test", test_state)]
    if prod_state is not None:
        return [entry("prod", prod_state)]
    return []


def squash(
    changelog: Changelog,
    definitions: dict[str, CheckDef],
    *,
    as_of: date,
    name: str,
) -> Changelog:
    """Collapse the changelog's history into a fresh baseline at ``as_of``.

    Rewrites the log as, in order:

    * value-free baseline entries (``effective`` = ``as_of``, no ``due``) reproducing the
      enforced state of every check per tier (tiers that agree collapse to ``tier: all``);
    * every still-pending or future-announced entry carried forward verbatim, so scheduled
      rollouts survive the squash; and
    * a new ``name`` tag pinned to ``as_of`` (older tags, no longer reproducible from the
      compacted log, are dropped and live on only in the archived snapshot the caller keeps).

    Baselines come first so the fold's last-wins tie-break lets a carried pending entry
    override its baseline once its ``due`` passes. Folding the result at ``as_of`` reproduces
    the input's rule set for every tier; the superseded history is dropped. Pure: no I/O.

    Raises :class:`VersionError` if ``name`` is malformed or already a tag.
    """
    if not _TAG_NAME_RE.match(name):
        raise VersionError(
            f"invalid conformance version name '{name}' (expected e.g. 2027.0)"
        )
    if name in changelog.tags:
        raise VersionError(f"conformance version '{name}' already exists")
    # Definitions are not needed to build the baseline, but a squash should only run on a log
    # whose checks all exist; surface a dangling reference rather than silently baselining it.
    unknown = sorted(changelog.check_ids - set(definitions))
    if unknown:
        raise RuleError(
            f"changelog references unknown check(s): {', '.join(unknown)}"
        )

    note = f"baseline {name}"
    baselines: list[ChangeEntry] = []
    for check_id in sorted(changelog.check_ids):
        test_state = _fold_check(
            _visible(changelog, check_id, "test", as_of), as_of
        )
        prod_state = _fold_check(
            _visible(changelog, check_id, "prod", as_of), as_of
        )
        baselines.extend(
            _baseline_entries(check_id, note, test_state, prod_state)
        )

    # Carry forward anything not yet fully applied: announced for the future, or still pending.
    carried = [
        e
        for e in changelog.entries
        if _parse_date(e.effective) > as_of
        or (e.due is not None and _parse_date(e.due) > as_of)
    ]

    tags = {n: d for n, d in changelog.tags.items() if _parse_date(d) >= as_of}
    tags[name] = as_of.isoformat()  # the version is pinned to the squash date
    return Changelog(entries=tuple(baselines + carried), tags=tags)


def changelog_lint(
    changelog: Changelog, definitions: dict[str, CheckDef]
) -> list[str]:
    """Return structural problems with the changelog (empty list means it is valid)."""
    violations: list[str] = []

    # Every entry targets a known check, and its dates are sane.
    for e in changelog.entries:
        if e.check_id not in definitions:
            violations.append(f"entry for unknown check '{e.check_id}'")
        if e.due is not None and _parse_date(e.due) < _parse_date(e.effective):
            violations.append(
                f"{e.check_id}: due {e.due} is before effective {e.effective}"
            )

    # No two entries collide on the same (check_id, tier, effective).
    seen: set = set()
    for e in changelog.entries:
        key = (e.check_id, e.tier, e.effective)
        if key in seen:
            violations.append(
                f"{e.check_id}: duplicate entry for tier '{e.tier}' effective {e.effective}"
            )
        seen.add(key)

    # Changes apply to test before prod: for one check and value, the test due date must
    # not be later than the prod due date.
    by_change: dict = {}
    for e in changelog.entries:
        if e.due is None or e.tier not in ("test", "prod"):
            continue
        by_change.setdefault((e.check_id, repr(e.value)), {})[e.tier] = e.due
    for change_key, dues in by_change.items():
        check_id = change_key[0]
        if "test" not in dues or "prod" not in dues:
            continue
        if _parse_date(dues["test"]) > _parse_date(dues["prod"]):
            violations.append(
                f"{check_id}: test due {dues['test']} is later than prod due {dues['prod']} "
                f"(changes must reach test before prod)"
            )

    return violations
