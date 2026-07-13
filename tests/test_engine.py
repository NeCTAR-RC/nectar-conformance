"""Engine evaluation: PASS / FAIL / SKIP / UNKNOWN, and pass+advisory rollouts."""

import dataclasses
from datetime import date

from conftest import (
    REGISTRY,
    VERSION,
    fixture_definitions,
    fixture_rules,
    make_node,
)

from nectar_conformance.engine.runner import evaluate
from nectar_conformance.engine.selectors import resolve as resolve_selector
from nectar_conformance.model import SiteModel
from nectar_conformance.results.model import Status
from nectar_conformance.rules.changelog import fold
from nectar_conformance.rules.model import ChangeEntry, Changelog
from nectar_conformance.rules.model import CheckDef, Rule, Selector

# Fold the frozen fixture changelog (see conftest), so adding shipped entries never breaks
# these engine tests. The default as_of is a date on which every fixture baseline is enforced.
_rules = fixture_rules


def _changelog(entries):
    return Changelog(
        entries=tuple(ChangeEntry.from_dict(e) for e in entries), tags={}
    )


# A nova-compute image-tag rollout from the baseline tag to a new one, used by the
# pass+advisory tests below. The baseline value matches the healthy site fixture.
_OLD_TAG = "27.5.1"
_NEW_TAG = "28.0.0"
_ROLLOUT = _changelog(
    [
        {
            "check_id": "nova.compute.image_tag",
            "value": _OLD_TAG,
            "effective": "2026-01-01",
        },
        {
            "check_id": "nova.compute.image_tag",
            "value": _NEW_TAG,
            "effective": "2026-06-01",
            "due": "2026-09-01",
        },
    ]
)


def _rollout_rules(as_of):
    return fold(_ROLLOUT, fixture_definitions(), tier="prod", as_of=as_of)


def _by_id(report):
    return {rr.rule_id: rr for rr in report.rule_results}


def test_healthy_site_all_pass(site_model):
    report = evaluate(site_model, _rules(), VERSION)
    results = _by_id(report)
    assert results["glance.api.image_tag"].status is Status.PASS
    assert results["glance.api.host_count"].status is Status.PASS
    assert results["mariadb.version"].status is Status.PASS
    assert results["ovn.version"].status is Status.PASS
    assert not report.has_failures
    assert report.score == 1.0


def test_image_tag_drift_fails(site_model):
    # Drift oc2's glance image to an old tag, leaving its other resources intact.
    nodes = list(site_model.nodes)
    idx = next(i for i, n in enumerate(nodes) if n.certname.startswith("oc2"))
    rewritten = []
    for r in nodes[idx].resources:
        if r.type == "Docker::Run" and r.title == "glance-api":
            r = dataclasses.replace(
                r,
                parameters={
                    "image": "registry.rc.nectar.org.au/kolla/ubuntu-source-glance-api:29.0.0-1"
                },
            )
        rewritten.append(r)
    nodes[idx] = dataclasses.replace(nodes[idx], resources=tuple(rewritten))
    model = dataclasses.replace(site_model, nodes=tuple(nodes))

    report = evaluate(model, _rules(), VERSION)
    rr = _by_id(report)["glance.api.image_tag"]
    assert rr.status is Status.FAIL
    failing = [c for c in rr.results if c.status is Status.FAIL]
    assert failing[0].node == "oc2.example.test"
    assert failing[0].remediation is not None
    assert report.has_failures


def test_selector_with_no_nodes_skips():
    # A site with only a controller: the compute image-tag check selects no nodes.
    model = SiteModel(
        "ardctest",
        "test",
        "2026-06-15T00:00:00Z",
        (
            make_node(
                "oc1.example.test",
                classes=["nectar::role::openstack::controller"],
            ),
        ),
    )
    report = evaluate(model, _rules(), VERSION)
    assert _by_id(report)["nova.compute.image_tag"].status is Status.SKIP


def test_missing_value_is_unknown(site_model):
    # Strip the mariadb apt repo resource so the version cannot be determined.
    nodes = [
        dataclasses.replace(n, resources=())
        if n.has_class("nectar::profile::mariadb::cluster")
        else n
        for n in site_model.nodes
    ]
    model = dataclasses.replace(site_model, nodes=tuple(nodes))
    report = evaluate(model, _rules(), VERSION)
    assert _by_id(report)["mariadb.version"].status is Status.UNKNOWN


def test_optional_count_skips_but_required_count_fails_when_absent():
    # An empty site: an optional service (swift) SKIPs its host-count check, but a
    # required one (rabbitmq, glance) FAILs because it must be present.
    empty = SiteModel("empty", "test", "2026-06-15T00:00:00Z", ())
    report = evaluate(empty, _rules(), VERSION)
    results = {rr.rule_id: rr.status for rr in report.rule_results}
    assert results["swift.storage.host_count"] is Status.SKIP
    assert results["rabbitmq.cluster.host_count"] is Status.FAIL
    assert results["glance.api.host_count"] is Status.FAIL
    # per-node checks still SKIP when no node matches the selector
    assert results["mariadb.version"] is Status.SKIP


def test_linuxbridge_present_fails_and_names_host(site_model):
    # Add a legacy node still running the linuxbridge agent package.
    from nectar_conformance.model import CatalogResource

    legacy = make_node(
        "cc9.example.test",
        classes=["nectar::profile::nova::compute", "systemd::networkd"],
        facts={"os": {"release": {"full": "22.04"}}},
        resources=[
            CatalogResource(
                "Package",
                "neutron-plugin-linuxbridge-agent",
                {"ensure": "present"},
            )
        ],
    )
    model = dataclasses.replace(site_model, nodes=site_model.nodes + (legacy,))
    report = evaluate(model, _rules(), VERSION)
    rr = _by_id(report)["neutron.linuxbridge_absent"]
    assert rr.status is Status.FAIL
    failing = [c.node for c in rr.results if c.status is Status.FAIL]
    assert failing == ["cc9.example.test"]


def test_count_fails_when_under_provisioned():
    # The service is present but below the required count -> FAIL (not SKIP).
    model = SiteModel(
        "ardctest",
        "test",
        "2026-06-15T00:00:00Z",
        (
            make_node(
                "oc1.example.test",
                classes=["nectar::profile::glance::api"],
            ),
        ),
    )
    report = evaluate(model, _rules(), VERSION)
    rr = _by_id(report)["glance.api.host_count"]
    assert rr.status is Status.FAIL  # 1 glance node, spec requires at least 2


def _set_nova_tag(site_model, tag):
    """Rewrite the nova-compute image tag on every compute node in the fixture."""
    nodes = []
    for n in site_model.nodes:
        if n.has_class("nectar::profile::nova::compute::container"):
            resources = [
                dataclasses.replace(
                    r, parameters={"image": f"{REGISTRY}-nova-compute:{tag}"}
                )
                if r.type == "Docker::Run" and r.title == "nova-compute"
                else r
                for r in n.resources
            ]
            n = dataclasses.replace(n, resources=tuple(resources))
        nodes.append(n)
    return dataclasses.replace(site_model, nodes=tuple(nodes))


def test_rollout_before_due_passes_with_advisory(site_model):
    # The site is on the old tag and the new tag's prod due date has not arrived.
    rr = _by_id(
        evaluate(site_model, _rollout_rules(date(2026, 7, 1)), VERSION)
    )["nova.compute.image_tag"]
    assert rr.status is Status.PASS
    assert rr.advisory is not None
    assert rr.advisory.upcoming_value == _NEW_TAG
    assert rr.advisory.due == "2026-09-01"
    assert rr.advisory.days == (date(2026, 9, 1) - date(2026, 7, 1)).days


def test_rollout_after_due_fails(site_model):
    # Past the due date the new tag is mandatory; a site still on the old tag FAILs.
    report = evaluate(site_model, _rollout_rules(date(2026, 9, 2)), VERSION)
    rr = _by_id(report)["nova.compute.image_tag"]
    assert rr.status is Status.FAIL
    assert report.has_failures


def test_rollout_early_adopter_passes_without_advisory(site_model):
    # A site already on the new tag passes outright, before the due date, with no advisory.
    model = _set_nova_tag(site_model, _NEW_TAG)
    rr = _by_id(evaluate(model, _rollout_rules(date(2026, 7, 1)), VERSION))[
        "nova.compute.image_tag"
    ]
    assert rr.status is Status.PASS
    assert rr.advisory is None


def test_rollout_wrong_value_fails_before_due(site_model):
    # A site on neither the old nor the new tag FAILs even within the grace window.
    model = _set_nova_tag(site_model, "99.0.0-garbage")
    rr = _by_id(evaluate(model, _rollout_rules(date(2026, 7, 1)), VERSION))[
        "nova.compute.image_tag"
    ]
    assert rr.status is Status.FAIL


# --- composite (all_of) selectors and fact_match presence matching ---

_COMPUTE = "nectar::profile::nova::compute"


def _kvm(module, nested):
    return {"kmods": {module: {"parameters": {"nested": nested}}}}


def _site(*nodes):
    return SiteModel("ardctest", "test", "2026-06-15T00:00:00Z", tuple(nodes))


def test_fact_match_present_selects_on_existence_not_value():
    model = _site(
        make_node("a.example.test", facts=_kvm("kvm_intel", "N")),
        make_node("b.example.test", facts=_kvm("kvm_intel", "Y")),
        make_node("c.example.test", facts=_kvm("kvm_amd", "0")),
    )
    sel = Selector(
        type="fact_match",
        params={"path": "kmods.kvm_intel", "match": "present"},
    )
    assert [n.certname for n in resolve_selector(model, sel)] == [
        "a.example.test",
        "b.example.test",
    ]


def test_fact_match_default_equality_unchanged():
    model = _site(
        make_node("a.example.test", facts=_kvm("kvm_intel", "N")),
        make_node("b.example.test", facts=_kvm("kvm_intel", "Y")),
    )
    sel = Selector(
        type="fact_match",
        params={"path": "kmods.kvm_intel.parameters.nested", "value": "Y"},
    )
    assert [n.certname for n in resolve_selector(model, sel)] == [
        "b.example.test"
    ]


def test_all_of_selector_intersects_clauses_preserving_site_order():
    model = _site(
        make_node(
            "cc1.example.test",
            classes=[_COMPUTE],
            facts=_kvm("kvm_intel", "N"),
        ),
        make_node("cc2.example.test", classes=[_COMPUTE]),  # class only
        make_node(
            "ci1.example.test", facts=_kvm("kvm_intel", "Y")
        ),  # fact only
        make_node(
            "cc3.example.test",
            classes=[_COMPUTE],
            facts=_kvm("kvm_intel", "Y"),
        ),
    )
    sel = Selector(
        type="all_of",
        params={
            "selectors": [
                {"type": "contains_class", "class": _COMPUTE},
                {
                    "type": "fact_match",
                    "path": "kmods.kvm_intel",
                    "match": "present",
                },
            ]
        },
    )
    assert [n.certname for n in resolve_selector(model, sel)] == [
        "cc1.example.test",
        "cc3.example.test",
    ]


def test_all_of_check_is_per_node_pass_fail_without_unknowns():
    # The nested-virt shape: scope by class AND module presence, then read the
    # module's fact. Other-vendor computes and non-compute hosts are simply not
    # selected, so a per-vendor check yields clean PASS/FAIL with no UNKNOWNNs.
    check = CheckDef.from_dict(
        {
            "id": "nova.compute.nested_virt.intel",
            "title": "Nested virtualisation is disabled on Intel compute nodes",
            "selector": {
                "type": "all_of",
                "selectors": [
                    {"type": "contains_class", "class": _COMPUTE},
                    {
                        "type": "fact_match",
                        "path": "kmods.kvm_intel",
                        "match": "present",
                    },
                ],
            },
            "query": {
                "type": "fact",
                "path": "kmods.kvm_intel.parameters.nested",
            },
            "assertion": {"op": "in_set"},
        }
    )
    rule = Rule(check=check, expected=["N", "0"])
    model = _site(
        make_node(
            "cc1.example.test",
            classes=[_COMPUTE],
            facts=_kvm("kvm_intel", "N"),
        ),
        make_node(
            "cc2.example.test",
            classes=[_COMPUTE],
            facts=_kvm("kvm_intel", "Y"),
        ),
        make_node(
            "cc3.example.test", classes=[_COMPUTE], facts=_kvm("kvm_amd", "1")
        ),
        make_node("ci1.example.test", facts=_kvm("kvm_intel", "Y")),
    )
    rr = evaluate(model, [rule], VERSION).rule_results[0]
    statuses = {c.node: c.status for c in rr.results}
    assert statuses == {
        "cc1.example.test": Status.PASS,
        "cc2.example.test": Status.FAIL,
    }
