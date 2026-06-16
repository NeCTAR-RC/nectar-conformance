"""Folding the conformance changelog: value binding, staggered rollout, tags, lint."""

from datetime import date

from conftest import (
    FIXTURE_TAG,
    FIXTURE_TAG_DATE,
    fixture_changelog,
    fixture_definitions,
)
import pytest

from nectar_conformance.errors import VersionError
from nectar_conformance.rules.changelog import (
    changelog_lint,
    fold,
    resolve_tag,
    squash,
)
from nectar_conformance.rules.model import ChangeEntry, Changelog

_OLD = "27.5.1"
_NEW = "28.0.0"


@pytest.fixture
def definitions():
    return fixture_definitions()


def _changelog(entries, tags=None):
    return Changelog(
        entries=tuple(ChangeEntry.from_dict(e) for e in entries),
        tags=tags or {},
    )


def _by_id(rules):
    return {r.id: r for r in rules}


# --- value binding (fold reads each entry's bound value into the rule) ---
# These fold the frozen fixture changelog (tests/fixtures/checks), not the shipped one, so
# appending real dated rollouts to the shipped changelog never breaks them.


def test_fold_binds_baseline_values(definitions):
    rules = _by_id(
        fold(
            fixture_changelog(),
            definitions,
            tier="prod",
            as_of=FIXTURE_TAG_DATE,
        )
    )
    assert rules["mariadb.version"].expected == "10.11"
    assert rules["glance.api.image_tag"].expected == "30.1.0"
    assert rules["ovn.version"].expected == "24.03"
    assert rules["rabbitmq.version"].expected == "3.13.7-1"
    assert rules["os.compute.ubuntu"].expected == ["24.04", "22.04"]
    assert rules["glance.api.host_count"].expected == 2
    # No baseline directive has a due date, so nothing is pending at the tag instant.
    assert all(not r.has_pending for r in rules.values())


# --- tags ---


def test_resolve_tag_and_unknown_raises():
    changelog = fixture_changelog()
    assert resolve_tag(changelog, FIXTURE_TAG) == FIXTURE_TAG_DATE
    with pytest.raises(VersionError):
        resolve_tag(changelog, "1999.9")


# --- staggered rollout: test sites enforce before prod sites ---


@pytest.fixture
def rollout():
    return _changelog(
        [
            {
                "check_id": "nova.compute.image_tag",
                "value": _OLD,
                "effective": "2026-01-01",
            },
            {
                "check_id": "nova.compute.image_tag",
                "value": _NEW,
                "effective": "2026-06-01",
                "due": "2026-06-20",
                "tier": "test",
            },
            {
                "check_id": "nova.compute.image_tag",
                "value": _NEW,
                "effective": "2026-06-01",
                "due": "2026-09-01",
                "tier": "prod",
            },
        ]
    )


def test_rollout_test_enforced_while_prod_pending(rollout, definitions):
    as_of = date(
        2026, 7, 1
    )  # after the test due date, before the prod due date
    cid = "nova.compute.image_tag"
    test_rule = _by_id(fold(rollout, definitions, tier="test", as_of=as_of))[
        cid
    ]
    prod_rule = _by_id(fold(rollout, definitions, tier="prod", as_of=as_of))[
        cid
    ]

    # Test tier: the change is mandatory.
    assert test_rule.expected == _NEW
    assert not test_rule.has_pending

    # Prod tier: the old value is still enforced, the new value is pending with a countdown.
    assert prod_rule.expected == _OLD
    assert prod_rule.has_pending
    assert prod_rule.pending_value == _NEW
    assert prod_rule.pending_due == "2026-09-01"
    assert prod_rule.pending_days == (date(2026, 9, 1) - as_of).days


def test_rollout_both_pending_before_any_due(rollout, definitions):
    as_of = date(2026, 6, 10)  # before both due dates
    for tier in ("test", "prod"):
        rule = _by_id(fold(rollout, definitions, tier=tier, as_of=as_of))[
            "nova.compute.image_tag"
        ]
        assert rule.expected == _OLD
        assert rule.has_pending and rule.pending_value == _NEW


def test_rollout_both_enforced_after_all_due(rollout, definitions):
    as_of = date(2026, 9, 2)  # after both due dates
    for tier in ("test", "prod"):
        rule = _by_id(fold(rollout, definitions, tier=tier, as_of=as_of))[
            "nova.compute.image_tag"
        ]
        assert rule.expected == _NEW
        assert not rule.has_pending


def test_fold_skips_not_yet_effective(definitions):
    changelog = _changelog(
        [
            {
                "check_id": "nova.compute.image_tag",
                "value": _NEW,
                "effective": "2027-01-01",
            },
        ]
    )
    rules = fold(changelog, definitions, tier="prod", as_of=date(2026, 7, 1))
    assert rules == []  # announced for the future, so not enforced yet


# --- lint ---
# The shipped-changelog lint guard now lives in the nectar-conformance-checks repo's CI
# (nectar-conformance changelog lint). These tests exercise the lint logic itself.


def test_lint_detects_prod_due_before_test_due(definitions):
    changelog = _changelog(
        [
            {
                "check_id": "nova.compute.image_tag",
                "value": _NEW,
                "effective": "2026-06-01",
                "due": "2026-09-01",
                "tier": "test",
            },
            {
                "check_id": "nova.compute.image_tag",
                "value": _NEW,
                "effective": "2026-06-01",
                "due": "2026-06-20",
                "tier": "prod",
            },  # prod earlier than test -> violation
        ]
    )
    violations = changelog_lint(changelog, definitions)
    assert any("test" in v and "prod" in v for v in violations)


def test_lint_detects_due_before_effective(definitions):
    changelog = _changelog(
        [
            {
                "check_id": "ovn.version",
                "value": "24.09",
                "effective": "2026-06-01",
                "due": "2026-05-01",
            },
        ]
    )
    assert changelog_lint(changelog, definitions)


def test_lint_detects_unknown_check(definitions):
    changelog = _changelog(
        [{"check_id": "no.such.check", "effective": "2026-01-01"}]
    )
    assert any(
        "no.such.check" in v for v in changelog_lint(changelog, definitions)
    )


# --- squash: compact the log into a fresh baseline without losing future behaviour ---


def _entries_for(changelog, check_id):
    return [e for e in changelog.entries if e.check_id == check_id]


def test_squash_collapses_superseded(definitions):
    # An old baseline plus a rollout whose due has passed: the old value is now dead history.
    changelog = _changelog(
        [
            {
                "check_id": "nova.compute.image_tag",
                "value": _OLD,
                "effective": "2026-01-01",
            },
            {
                "check_id": "nova.compute.image_tag",
                "value": _NEW,
                "effective": "2026-06-01",
                "due": "2026-06-20",
            },
        ]
    )
    squashed = squash(
        changelog, definitions, as_of=date(2026, 7, 1), name="2027.0"
    )
    entries = _entries_for(squashed, "nova.compute.image_tag")
    assert len(entries) == 1  # the superseded _OLD entry is gone
    assert entries[0].value == _NEW
    assert entries[0].tier == "all"
    assert entries[0].due is None
    assert squashed.tags["2027.0"] == "2026-07-01"
    rule = _by_id(
        fold(squashed, definitions, tier="prod", as_of=date(2026, 7, 1))
    )["nova.compute.image_tag"]
    assert rule.expected == _NEW and not rule.has_pending


def test_squash_preserves_pending(rollout, definitions):
    # Squash before either due date: the scheduled rollout must survive intact.
    squashed = squash(
        rollout, definitions, as_of=date(2026, 6, 10), name="2026.5"
    )
    cid = "nova.compute.image_tag"

    for tier in ("test", "prod"):
        rule = _by_id(
            fold(squashed, definitions, tier=tier, as_of=date(2026, 6, 10))
        )[cid]
        assert rule.expected == _OLD
        assert rule.has_pending and rule.pending_value == _NEW

    # The carried-forward dues still fire on schedule, test before prod.
    test_after = _by_id(
        fold(squashed, definitions, tier="test", as_of=date(2026, 7, 1))
    )[cid]
    prod_after = _by_id(
        fold(squashed, definitions, tier="prod", as_of=date(2026, 9, 2))
    )[cid]
    assert test_after.expected == _NEW
    assert prod_after.expected == _NEW


def test_squash_preserves_tier_split(rollout, definitions):
    # Squash after the test due but before the prod due: tiers disagree, so emit per-tier.
    squashed = squash(
        rollout, definitions, as_of=date(2026, 7, 1), name="2026.6"
    )
    cid = "nova.compute.image_tag"
    tiers = {e.tier for e in _entries_for(squashed, cid)}
    assert "test" in tiers and "prod" in tiers and "all" not in tiers

    test_rule = _by_id(
        fold(squashed, definitions, tier="test", as_of=date(2026, 7, 1))
    )[cid]
    prod_rule = _by_id(
        fold(squashed, definitions, tier="prod", as_of=date(2026, 7, 1))
    )[cid]
    assert test_rule.expected == _NEW and not test_rule.has_pending
    assert prod_rule.expected == _OLD and prod_rule.has_pending


def test_squash_collapses_agreeing_tiers(definitions):
    # A pure baseline (test and prod agree) collapses to a single tier: all entry.
    squashed = squash(
        fixture_changelog(),
        definitions,
        as_of=FIXTURE_TAG_DATE,
        name="2099.0",
    )
    for entry in squashed.entries:
        assert entry.tier == "all"
    rules = _by_id(
        fold(squashed, definitions, tier="prod", as_of=FIXTURE_TAG_DATE)
    )
    assert rules["mariadb.version"].expected == "10.11"
    assert rules["glance.api.image_tag"].expected == "30.1.0"


def test_squash_manages_tags_and_lints_clean(definitions):
    changelog = _changelog(
        [
            {
                "check_id": "ovn.version",
                "value": "24.03",
                "effective": "2026-01-01",
            },
            {
                "check_id": "ovn.version",
                "value": "24.09",
                "effective": "2026-12-01",  # announced for after the squash
            },
        ],
        tags={"2026.1": "2026-03-01", "2099.9": "2026-12-15"},
    )
    squashed = squash(
        changelog, definitions, as_of=date(2026, 7, 1), name="2026.7"
    )
    # The new tag is added; tags on/after the squash date survive; older ones are dropped.
    assert squashed.tags["2026.7"] == "2026-07-01"
    assert "2099.9" in squashed.tags
    assert "2026.1" not in squashed.tags
    # The future-announced entry is carried forward verbatim.
    assert any(e.effective == "2026-12-01" for e in squashed.entries)
    assert changelog_lint(squashed, definitions) == []


def test_squash_rejects_bad_or_duplicate_name(definitions):
    changelog = _changelog(
        [
            {
                "check_id": "ovn.version",
                "value": "24.03",
                "effective": "2026-01-01",
            }
        ],
        tags={"2026.1": "2026-03-01"},
    )
    with pytest.raises(VersionError):
        squash(changelog, definitions, as_of=date(2026, 7, 1), name="2027")
    with pytest.raises(VersionError):
        squash(changelog, definitions, as_of=date(2026, 7, 1), name="2026.1")


def test_squash_is_faithful_across_future_dates(rollout, definitions):
    # Folding the squashed log must match the original for every date on/after the squash.
    def behaviour(cl, tier, as_of):
        return {
            r.id: (r.expected, r.has_pending, r.pending_value, r.pending_due)
            for r in fold(cl, definitions, tier=tier, as_of=as_of)
        }

    squash_date = date(2026, 6, 10)
    squashed = squash(rollout, definitions, as_of=squash_date, name="2026.9")
    for delta in (0, 11, 25, 95, 200):
        d = date.fromordinal(squash_date.toordinal() + delta)
        for tier in ("test", "prod"):
            assert behaviour(rollout, tier, d) == behaviour(squashed, tier, d)
