"""Static-repo data source: build a model from compiled catalog JSON."""

from conftest import (
    CATALOG_DIR,
    FACTS_DIR,
    FIXTURE_TAG_DATE,
    VERSION,
    fixture_rules,
)

from nectar_conformance.config import Config
from nectar_conformance.datasources.static_repo import (
    StaticRepoDataSource,
    _node_from_catalog,
)
from nectar_conformance.engine.runner import evaluate
from nectar_conformance.results.model import Status


def _load():
    source = StaticRepoDataSource(
        Config(), catalog_dir=str(CATALOG_DIR), facts_dir=str(FACTS_DIR)
    )
    return source.load_site("ardctest")


def test_static_source_builds_model():
    model = _load()
    assert model.source == "static_repo"
    certnames = {n.certname for n in model.nodes}
    assert "oc1.example.test" in certnames
    oc1 = next(n for n in model.nodes if n.certname.startswith("oc1"))
    assert oc1.has_class("nectar::profile::glance::api")
    assert oc1.resource("Docker::Run", "glance-api") is not None
    db1 = next(n for n in model.nodes if n.certname.startswith("db1"))
    assert db1.facts.get("mariadb.version") == "10.11"


def test_node_from_puppetdb_shaped_catalog():
    # PuppetDB's catalog/resources shape nests resources under {"data": [...]}.
    catalog = {
        "certname": "x.example",
        "environment": "ardctest",
        "resources": {
            "data": [
                {"type": "Class", "title": "Nectar::Profile::Glance::Api"},
                {
                    "type": "Docker::Run",
                    "title": "glance-api",
                    "parameters": {"image": "r:1"},
                },
            ]
        },
    }
    node = _node_from_catalog(catalog, "ardctest", "ardctest", {})
    assert node.has_class("nectar::profile::glance::api")
    assert node.resource("Docker::Run", "glance-api") is not None


def test_static_source_drift_detected():
    model = _load()
    rules = fixture_rules(tier="prod", as_of=FIXTURE_TAG_DATE)
    report = evaluate(model, rules, VERSION)
    results = {rr.rule_id: rr.status for rr in report.rule_results}
    # oc2's catalog pins an old glance tag.
    assert results["glance.api.image_tag"] is Status.FAIL
    assert results["glance.api.host_count"] is Status.PASS
    assert report.has_failures
