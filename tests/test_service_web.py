"""Web dashboard service helpers: discovery and changelog views.

list_changes / pending_changes / timeline are exercised against a *controlled* checks dir
(the mirrored definitions + a small hand-authored changelog) so the assertions are not
coupled to the real changelog's evolving values.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import shutil

import pytest

from nectar_conformance.config import DEFAULT_SITES, Config
from nectar_conformance.datasources import puppetdb
from nectar_conformance.service import (
    change_history,
    change_timeline,
    discover_sites,
    list_changes,
    pending_changes,
)

AS_OF = date(2026, 6, 17)

# A controlled changelog over the real rabbitmq.version definition: a baseline value plus a
# dated upgrade that is pending at AS_OF (effective passed, due in the future).
CONTROLLED_CHANGELOG = """---
tags:
  "2099.0": "2099-01-01"
entries:
  - {check_id: rabbitmq.version, value: "1.0", effective: "2026-01-01"}
  - {check_id: rabbitmq.version, value: "2.0", effective: "2026-06-01", due: "2026-12-01", tier: prod, note: "upgrade rabbit"}
"""


@pytest.fixture
def controlled_config(tmp_path) -> Config:
    mirror = Path(__file__).parent / "fixtures" / "checks"
    checks_dir = tmp_path / "checks"
    shutil.copytree(mirror, checks_dir)
    (checks_dir / "changelog.yaml").write_text(CONTROLLED_CHANGELOG)
    return Config(checks_dir=str(checks_dir))


def _no_puppetdb(monkeypatch):
    def explode(self, base_url=None):
        raise AssertionError("PuppetDB must not be queried")

    monkeypatch.setattr(
        puppetdb.PuppetDBDataSource, "list_environments", explode
    )


def test_discover_sites_uses_builtin_defaults(monkeypatch):
    # No config, no flags: dev and the deployments share the built-in per-tier lists.
    _no_puppetdb(monkeypatch)
    assert [
        s["site"] for s in discover_sites(Config(), tier="prod")
    ] == sorted(DEFAULT_SITES["prod"])
    assert [
        s["site"] for s in discover_sites(Config(), tier="test")
    ] == sorted(DEFAULT_SITES["test"])


def test_discover_sites_uses_configured_allowlist(monkeypatch):
    _no_puppetdb(monkeypatch)  # configured allowlist must not hit PuppetDB
    cfg = Config(sites={"prod": ["site1", "ardc"], "test": ["ardctest"]})
    assert discover_sites(cfg, tier="prod") == [
        {"site": "ardc", "environment": "ardc"},
        {"site": "site1", "environment": "site1"},
    ]
    assert discover_sites(cfg, tier="test") == [
        {"site": "ardctest", "environment": "ardctest"}
    ]


def test_discover_sites_falls_back_to_discovery_for_unknown_tier(monkeypatch):
    # A tier with neither a configured nor a built-in list enumerates PuppetDB.
    monkeypatch.setattr(
        puppetdb.PuppetDBDataSource,
        "list_environments",
        lambda self, base_url=None: ["site1", "ardc"],
    )
    assert discover_sites(Config(), tier="staging") == [
        {"site": "ardc", "environment": "ardc"},
        {"site": "site1", "environment": "site1"},
    ]


def test_discover_sites_applies_environment_override(monkeypatch):
    monkeypatch.setattr(
        puppetdb.PuppetDBDataSource,
        "list_environments",
        lambda self, base_url=None: ["branch-env"],
    )
    cfg = Config(site_environment={"site1": "branch-env"})
    assert discover_sites(cfg, tier="staging") == [
        {"site": "site1", "environment": "branch-env"}
    ]


def test_list_changes_carries_op_and_target(controlled_config):
    changes = list_changes(controlled_config, tier="prod", as_of=AS_OF)
    assert len(changes) == 1
    change = changes[0]
    assert change["check_id"] == "rabbitmq.version"
    assert change["op"] == "equals"
    assert change["target"] == "2.0"
    assert change["due"] == "2026-12-01"
    assert change["tier"] == "prod"


def test_list_changes_excludes_other_tier(controlled_config):
    # The dated change is tier prod; a test-tier view should not see it.
    assert list_changes(controlled_config, tier="test", as_of=AS_OF) == []


def test_pending_changes_surfaces_upcoming_value(controlled_config):
    pending = pending_changes(controlled_config, tier="prod", as_of=AS_OF)
    rabbit = [r for r in pending if r.id == "rabbitmq.version"]
    assert len(rabbit) == 1
    assert rabbit[0].expected == "1.0"  # still enforced today
    assert rabbit[0].pending_value == "2.0"  # the upcoming target
    assert rabbit[0].pending_due == "2026-12-01"


def test_change_timeline_filters_by_tier(controlled_config):
    # Ordered by effective; no tier filter shows every directive.
    assert [e["value"] for e in change_timeline(controlled_config)] == [
        "1.0",
        "2.0",
    ]
    prod = change_timeline(controlled_config, tier="prod")
    assert [e["value"] for e in prod] == ["1.0", "2.0"]
    # The prod-only upgrade is hidden from a test deployment; the neutral baseline stays.
    test = change_timeline(controlled_config, tier="test")
    assert [e["value"] for e in test] == ["1.0"]


def test_change_history(controlled_config):
    assert len(change_history(controlled_config, "rabbitmq.version")) == 2
    assert (
        len(change_history(controlled_config, "rabbitmq.version", tier="test"))
        == 1
    )
    assert change_history(controlled_config, "no.such.check") == []
