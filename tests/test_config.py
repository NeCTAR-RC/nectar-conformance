"""Tier resolution, env/file layering, and PuppetDB token/endpoint resolution."""

import pytest

from nectar_conformance.config import (
    DEFAULT_PUPPETDB_URLS,
    DEFAULT_TEST_SITES,
    Config,
    PuppetDBConfig,
    load,
)
from nectar_conformance.errors import ConfigError


def test_builtin_test_sites_resolve_to_test():
    config = Config()
    for site in DEFAULT_TEST_SITES:
        assert config.site_tier_for(site) == "test"


def test_unknown_site_defaults_to_prod():
    assert Config().site_tier_for("site1") == "prod"


def test_explicit_config_overrides_builtin():
    # A built-in test site can be pinned back to prod, and an arbitrary site to test.
    config = Config(site_tier={"ardctest": "prod", "somewhere": "test"})
    assert config.site_tier_for("ardctest") == "prod"
    assert config.site_tier_for("somewhere") == "test"
    # Other built-ins still resolve to test.
    assert config.site_tier_for("site1test") == "test"


def test_env_layering(monkeypatch):
    monkeypatch.setenv("NECTAR_CONFORMANCE_PUPPETDB_URL", "http://pdb:8080")
    monkeypatch.setenv("NECTAR_CONFORMANCE_SOURCE", "static")
    cfg = load()
    assert cfg.puppetdb.base_url == "http://pdb:8080"
    assert cfg.source == "static"


def test_load_file_and_overrides(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("source: static\nsites:\n  prod: [a, b]\n")
    cfg = load(str(path), overrides={"source": "puppetdb"})
    assert cfg.source == "puppetdb"  # explicit override wins over the file
    assert cfg.sites_for("prod") == ["a", "b"]


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load(str(tmp_path / "nope.yaml"))


def test_resolved_token_from_file(tmp_path):
    token = tmp_path / "token"
    token.write_text("  secret\n")
    assert PuppetDBConfig(token_file=str(token)).resolved_token() == "secret"
    assert PuppetDBConfig(token="inline").resolved_token() == "inline"
    assert PuppetDBConfig().resolved_token() is None


def test_resolved_token_missing_file(tmp_path):
    with pytest.raises(ConfigError):
        PuppetDBConfig(token_file=str(tmp_path / "absent")).resolved_token()


def test_puppetdb_base_url_for_per_tier_default():
    cfg = Config()
    assert (
        cfg.puppetdb_base_url_for("ardctest") == DEFAULT_PUPPETDB_URLS["test"]
    )
    assert cfg.puppetdb_base_url_for("site1") == DEFAULT_PUPPETDB_URLS["prod"]
    explicit = Config(puppetdb=PuppetDBConfig(base_url="http://x:8080"))
    assert explicit.puppetdb_base_url_for("site1") == "http://x:8080"
