"""Shared test fixtures and helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nectar_conformance.model import (
    CatalogResource,
    FactSet,
    NodeModel,
    SiteModel,
)
from nectar_conformance.rules.changelog import fold
from nectar_conformance.rules.loader import load_changelog, load_definitions

FIXTURES = Path(__file__).parent / "fixtures"
CATALOG_DIR = FIXTURES / "catalogs"
FACTS_DIR = FIXTURES / "facts"

# A self-contained checks dir owned by the test suite: a frozen changelog
# (tests/fixtures/checks/changelog.yaml) plus a mirror of the real definitions under
# definitions/. The check data proper lives in the nectar-conformance-checks repo, so the
# suite carries its own copy and never depends on an external checkout. Behavioural tests
# fold this frozen changelog so a real dated rollout in that repo never forces a test
# update. See the changelog's header.
CHECKS_FIXTURE = FIXTURES / "checks"
# A date on which every fixture baseline directive is enforced and none is pending.
FIXTURE_AS_OF = date(2026, 6, 15)
# The fixture changelog's pinned tag and the date it resolves to.
FIXTURE_TAG = "2026.1"
FIXTURE_TAG_DATE = date(2026, 3, 1)
# Label put in reports for fixture-based runs (just a string; not tied to the changelog).
VERSION = "2026.1"

REGISTRY = "registry.rc.nectar.org.au/kolla/ubuntu-source"
UBUNTU = {"os": {"release": {"full": "24.04"}}}
# Network nodes are pinned to 22.04 in the fixture spec.
UBUNTU_JAMMY = {"os": {"release": {"full": "22.04"}}}


def fixture_changelog():
    """Load the frozen test changelog (tests/fixtures/checks/changelog.yaml)."""
    return load_changelog(str(CHECKS_FIXTURE))


def fixture_definitions():
    """Load the mirrored check definitions (tests/fixtures/checks/definitions)."""
    return load_definitions(str(CHECKS_FIXTURE))


def fixture_rules(tier="prod", as_of=FIXTURE_AS_OF):
    """Fold the frozen test changelog with the fixture definitions into a rule set."""
    return fold(
        fixture_changelog(), fixture_definitions(), tier=tier, as_of=as_of
    )


def make_node(certname, classes=(), facts=None, resources=(), site="ardctest"):
    return NodeModel(
        certname=certname,
        environment=site,
        site_id=site,
        facts=FactSet(facts if facts is not None else {}),
        classes=tuple(classes),
        resources=tuple(resources),
        source="test",
    )


def _docker(title, tag):
    return CatalogResource(
        "Docker::Run", title, {"image": f"{REGISTRY}-{title}:{tag}"}
    )


def _ovn_repo(version="24.03"):
    return CatalogResource(
        "Class", "profile::core::ovn_repo", {"version": version}
    )


@pytest.fixture
def glance_resource():
    """The approved glance-api Docker::Run, reused by the image-tag drift test."""
    return _docker("glance-api", "30.1.0")


@pytest.fixture
def site_model(glance_resource):
    """A complete, healthy ardctest-like site: every fixture-changelog check passes."""
    nodes = []

    # Controllers (oc): glance, cinder, nova control plane.
    for i in (1, 2):
        nodes.append(
            make_node(
                f"oc{i}.example.test",
                classes=[
                    "nectar::role::openstack::controller",
                    "nectar::profile::glance::api",
                    "nectar::profile::cinder::volume",
                    "nectar::profile::nova::conductor",
                    "nectar::profile::nova::novnc",
                    "nectar::profile::iscsid",
                    "systemd::networkd",
                ],
                facts=UBUNTU,
                resources=[
                    glance_resource,
                    _docker("cinder-volume", "24.0.0"),
                    _docker("nova-conductor", "27.5.0"),
                    _docker("nova-novncproxy", "27.5.0"),
                    _docker("iscsid", "2024.1-6"),
                ],
            )
        )

    # Compute (cc): nova-compute, ceilometer, neutron, OVN.
    for i in (1, 2):
        nodes.append(
            make_node(
                f"cc{i}.example.test",
                classes=[
                    "nectar::profile::nova::compute",
                    "nectar::profile::nova::compute::container",
                    "nectar::profile::ceilometer::agent_compute",
                    "nectar::profile::neutron::neutron_ovn_metadata_container",
                    "profile::core::ovn_repo",
                    "systemd::networkd",
                ],
                facts=UBUNTU,
                resources=[
                    _docker("nova-compute", "27.5.1"),
                    _docker("ceilometer-compute", "20.0.0"),
                    _docker(
                        "neutron-ovn-metadata-agent",
                        "22.2.1",
                    ),
                    _ovn_repo(),
                ],
            )
        )

    # Database (db): MariaDB Galera cluster.
    mariadb_repo = CatalogResource(
        "Apt::Source",
        "mariadb",
        {
            "location": "http://mirror.aarnet.edu.au/pub/MariaDB/repo/10.11/ubuntu"
        },
    )
    for i in (1, 2, 3):
        nodes.append(
            make_node(
                f"db{i}.example.test",
                classes=[
                    "nectar::role::db::cluster",
                    "nectar::profile::mariadb::cluster",
                    "systemd::networkd",
                ],
                facts=UBUNTU,
                resources=[mariadb_repo],
            )
        )

    # Message queue (mq): RabbitMQ + Erlang pins.
    rabbit_pin = CatalogResource(
        "Apt::Pin", "pin-rabbitmq-server", {"version": "3.13.7-1"}
    )
    erlang_pin = CatalogResource(
        "Apt::Pin", "pin-erlang", {"version": "1:26.2.5.*"}
    )
    for i in (1, 2, 3):
        nodes.append(
            make_node(
                f"mq{i}.example.test",
                classes=[
                    "nectar::role::mq::cluster",
                    "nectar::profile::rabbitmq::cluster",
                    "systemd::networkd",
                ],
                facts=UBUNTU,
                resources=[rabbit_pin, erlang_pin],
            )
        )

    # Network (nc): neutron controller + OVN.
    for i in (1, 2):
        nodes.append(
            make_node(
                f"nc{i}.example.test",
                classes=[
                    "nectar::role::network_node::base",
                    "nectar::role::neutron::controller",
                    "profile::core::ovn_repo",
                    "systemd::networkd",
                ],
                facts=UBUNTU_JAMMY,
                resources=[_ovn_repo()],
            )
        )

    # Swift storage (ss): object store, at least the replica count.
    for i in (1, 2, 3):
        nodes.append(
            make_node(
                f"ss{i}.example.test",
                classes=[
                    "nectar::role::swift::storage",
                    "nectar::profile::swift::storage",
                    "systemd::networkd",
                ],
                facts=UBUNTU,
            )
        )

    # Swift proxy (sp).
    nodes.append(
        make_node(
            "swiftproxy1.example.test",
            classes=[
                "nectar::role::swift::proxy",
                "nectar::profile::swift::proxy",
                "systemd::networkd",
            ],
            facts=UBUNTU,
        )
    )

    # Proxy (admin/user) and wagnet router nodes: two of each for redundancy.
    for prefix, role in (
        ("pa", "nectar::role::proxy::admin"),
        ("pu", "nectar::role::proxy::user"),
        ("wr", "nectar::role::wagnet::router"),
    ):
        for i in (1, 2):
            nodes.append(
                make_node(
                    f"{prefix}{i}.example.test",
                    classes=[role, "systemd::networkd"],
                    facts=UBUNTU,
                )
            )

    return SiteModel("ardctest", "test", "2026-06-15T00:00:00Z", tuple(nodes))
