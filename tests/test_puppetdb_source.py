"""PuppetDB data source: build a model from mocked PQL responses."""

from nectar_conformance.config import (
    DEFAULT_PUPPETDB_URLS,
    Config,
    PuppetDBConfig,
)
from nectar_conformance.datasources.puppetdb import PuppetDBDataSource

CERT = "oc1.example.test"


def _fake_pql(query: str):
    if query.startswith("nodes["):
        return [{"certname": CERT}]
    if query.startswith("facts["):
        return [
            {
                "certname": CERT,
                "name": "os",
                "value": {"release": {"full": "24.04"}},
            },
            {"certname": CERT, "name": "datacenter", "value": "dc1"},
        ]
    if 'type = "Class"' in query:
        return [
            {"certname": CERT, "title": "Nectar::Profile::Glance::Api"},
            {"certname": CERT, "title": "Systemd::Networkd"},
        ]
    if query.startswith("resources[certname, type, title, parameters]"):
        image = (
            "registry.rc.nectar.org.au/kolla/ubuntu-source-glance-api:30.1.0"
        )
        return [
            {
                "certname": CERT,
                "type": "Docker::Run",
                "title": "glance-api",
                "parameters": {"image": image},
            }
        ]
    raise AssertionError(f"unexpected query: {query}")


def test_puppetdb_source_builds_model():
    cfg = Config(
        puppetdb=PuppetDBConfig(base_url="https://puppetdb.example:8081")
    )
    source = PuppetDBDataSource(cfg, resource_types={"Docker::Run"})
    source._pql = _fake_pql  # bypass HTTP

    model = source.load_site("ardctest")
    assert len(model.nodes) == 1
    node = model.nodes[0]
    assert node.certname == CERT
    assert node.environment == "ardctest"
    assert node.has_class("nectar::profile::glance::api")  # case-insensitive
    assert node.facts.get("os.release.full") == "24.04"
    assert node.datacenter == "dc1"
    res = node.resource("Docker::Run", "glance-api")
    assert res is not None and "glance-api:30.1.0" in res.parameters["image"]


def test_puppetdb_source_filters_by_environment():
    cfg = Config(
        puppetdb=PuppetDBConfig(base_url="https://puppetdb.example:8081")
    )
    cfg.site_environment = {"ardctest": "ardctest"}
    source = PuppetDBDataSource(cfg)
    seen = {}

    def capture(query):
        if query.startswith("nodes["):
            seen["nodes"] = query
            return [{"certname": CERT}]
        return []

    source._pql = capture
    source.load_site("ardctest")
    assert 'catalog_environment = "ardctest"' in seen["nodes"]


def _nodes_only(query: str):
    return [{"certname": CERT}] if query.startswith("nodes[") else []


def test_default_url_follows_site_tier():
    # No base_url configured: a known test site uses the rctest default, a prod site
    # uses the production default. The endpoint is resolved per site in load_site.
    cfg = Config()

    test_source = PuppetDBDataSource(cfg)
    test_source._pql = _nodes_only
    test_source.load_site("ardctest")
    assert test_source._base_url == DEFAULT_PUPPETDB_URLS["test"]

    prod_source = PuppetDBDataSource(cfg)
    prod_source._pql = _nodes_only
    prod_source.load_site("site1")
    assert prod_source._base_url == DEFAULT_PUPPETDB_URLS["prod"]


def test_explicit_url_overrides_tier_default():
    cfg = Config(
        puppetdb=PuppetDBConfig(base_url="https://override.example:8081")
    )
    source = PuppetDBDataSource(cfg)
    source._pql = _nodes_only
    # ardctest is a test site that would otherwise use the rctest default.
    source.load_site("ardctest")
    assert source._base_url == "https://override.example:8081"
